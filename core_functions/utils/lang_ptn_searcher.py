## encoding: utf-8

"""
Search Pattern

This module contains various search functions that serve different search purposes.
Single word search: search for a single word with specified wordform, and/or part of speech, and/or syntactic functions expressed by dependence type.
"""
from dataclasses import dataclass
from collections import defaultdict

from spacy.matcher import DependencyMatcher, PhraseMatcher

import math


# QCoreApplication.translate 允许你在非 QObject 类中标记和翻译字符串（静态翻译方法）
from PySide6.QtCore import QCoreApplication


@dataclass
class Query:
    """
    Query class
    ==============
    Each Query contains a specification for one word
    """    
    
    def __init__(self, wordform="", lemma="", pos="", dep="", phrase="", dep_struct="") -> None:
        self.wordform = wordform
        self.lemma = lemma
        self.pos = pos
        self.dep = dep
        self.phrase = phrase
        self.dep_struct = dep_struct
        self.identify_name()
        
    def identify_name(self):
        if self.phrase != "": 
            self.name = self.phrase
        elif self.dep_struct != "": 
            self.name = self.dep_struct
        else: 
            self.name = "{}_{}_{}".format(self.wordform, self.lemma, self.pos)



class LingPatternSearcher():
    def __init__(self) -> None:
        pass

    def _tr(self, text):
        # Qt静态翻译：第一个参数是 Context (上下文)，通常写类名，方便在翻译软件里归类
        return QCoreApplication.translate("LingPatternSearcher", text)

    @classmethod
    def search_for_phrase(self, matcher, phrase, nlp_api):
        """
        Search for phrase
        ===========
        Args:
            matcher (spacy.PhraseMatcher):
            phrase_list: a string list
            nlp_api: spacy api
        """
        matcher.add(phrase, [nlp_api.nlp(phrase)])
        
        return matcher
        
    @classmethod
    def single_word_search(self, matcher, wordform="", lemma="", pos="", dep=""):
        """Search for single word.

        Args:
            matcher (_type_): _description_
            wordform (str, optional): _description_. Defaults to "".
            lemma (str, optional): _description_. Defaults to "".
            pos (str, optional): _description_. Defaults to "".
            dep (str, optional): _description_. Defaults to "".

        Returns:
            _type_: _description_
        """
        # 根据有效字段命名匹配模式，之后匹配结果会形如：[(match_id, [token_index])]
        if len(wordform) > 0: match_id = wordform
        elif len(lemma) > 0:  match_id = lemma
        elif len(pos) > 0:    match_id = pos
        elif len(dep) > 0:    match_id = dep
        else: match_id = "single_word" # 所有字段都为空，则默认名为 single_word

        # 构造一个 token 应该满足的属性条件字典，例如：
        # 要求 {LEMMA="go"，POS="VERB"} 意味着：找到所有 lemma 为 “go” 的动词 token
        attrs = dict()
        if len(wordform) > 0: attrs["TEXT"] = wordform
        if len(lemma) > 0:    attrs["LEMMA"] = lemma
        if len(pos) > 0:      attrs["POS"] = pos
        if len(dep) > 0:      attrs["DEP"] = dep
        ptn = [{"RIGHT_ID": "right_id", 
                "RIGHT_ATTRS": attrs}] # 匹配一个 token，它的属性 RIGHT_ATTRS 满足 attrs 中的条件。

        matcher.add(match_id, [ptn]) # 把该模式注册到 matcher
        
        return matcher

        
    @classmethod
    def search_in_spacy_doc(self, 
                            spacy_doc, 
                            nlp_api, 
                            query_list, 
                            srch_mode=1,
                            batch_size=5000,
                            reporter=None):
        """Search for sentences that satisfy any in the query_list in a spaCy Doc.
        
        Args:
            spacy_doc (_type_): a spaCy Doc object.
            nlp_api (SpacyApi): the spaCy api that generates the spacy_doc.
            query_list (list of Query): a list of Query objects
            srch_mode (int, optional): Define the search mode. Defaults to 1.
                1: search for sentences with given single words; 
                2: search for sentences with given phrases.
            batch_size (int, optional): 按多少句为一批进行匹配检索。
            reporter (ProgressReporter, optional): 进度回调对象。

        Returns:
            (list(spacy.sent), dict(str,freq)): a list of shot sentences that satisfy the quests,
             and a dictionary that contains the frequency of matched ids.
        """
        # ========== 1. 构建 matcher ==========
        if srch_mode == 1:
            ## Single word search mode
            matcher = DependencyMatcher(nlp_api.nlp.vocab)
            for query in query_list:
                # 注册匹配模式
                self.single_word_search(matcher, 
                                        wordform=query.wordform, 
                                        lemma=query.lemma, 
                                        pos=query.pos, 
                                        dep=query.dep)
            
        elif srch_mode == 2:
            ## phrase search mode
            matcher = PhraseMatcher(nlp_api.nlp.vocab, attr="LOWER")
            for query in query_list:
                self.search_for_phrase(matcher, query.phrase, nlp_api)
        
        # ========== 2. 按句子切batch进行遍历匹配 ==========
        # 2.1 切分句子
        sents = list(spacy_doc.sents)
        total_sents = len(sents)
        if batch_size <= 0:
            batch_size = total_sents  # 退化为“整篇一次”

        # 计算批次数，方便进度计算
        total_batches = math.ceil(total_sents / batch_size)

        # 2.2 为最终结果准备容器
        matched_sents = []              # 用于存放“匹配到的句子对象”
        matched_index = set()           # 避免收集重复句子
        srchid2freq = defaultdict(int)  # 每个 pattern 的命中次数

        # 2.3 遍历 batch
        for batch_idx in range(total_batches):
            # 进度更新（以 batch 为单位）
            if reporter:
                pct = int((batch_idx + 1) / total_batches * 100)
                reporter.report(pct, QCoreApplication.translate("LingPatternSearcher", "检索语料[{}/{}]……").format(batch_idx+1, total_batches))

            # 当前批次的句子范围
            start_sent_idx = batch_idx * batch_size
            end_sent_idx = min((batch_idx + 1) * batch_size, total_sents)

            first_sent = sents[start_sent_idx]
            last_sent = sents[end_sent_idx - 1]

            batch_start = first_sent.start
            batch_end = last_sent.end  # spaCy 切片是 [start:end)

            sub_span = spacy_doc[batch_start:batch_end]
            sub_doc = sub_span.as_doc()  # 重新构造一个局部 Doc 交给 matcher

            # -------- 对切块进行匹配检索 --------
            batch_matches = matcher(sub_doc)

            if srch_mode == 1:
                # DependencyMatcher 每个匹配结果格式：(match_id, [token_indices])
                for match_id, index_list in batch_matches:
                    # index_list 里是局部 sub_doc 内的索引
                    for local_pos in index_list:
                        srchid2freq[match_id] += 1 # 累计每种 match_id 的频次，例如“run” 这个 lemma 共出现多少次？“verb” 这个 POS 匹配了多少次？
                        # 我们要把它映射回原 doc 的绝对索引
                        global_pos = batch_start + local_pos
                        # 定位 token 所在的句子
                        sent = spacy_doc[global_pos].sent
                        if sent[0].i not in matched_index:
                            matched_sents.append(sent)
                            matched_index.add(sent[0].i)

            elif srch_mode == 2:
                # PhraseMatcher: (match_id, start, end)
                # 尚未修改实装，todo
                for match_id, start, end in batch_matches:
                    srchid2freq[match_id] += 1
                    global_start = batch_start + start
                    sent = spacy_doc[global_start].sent
                    if sent[0].i not in matched_index:
                        matched_sents.append(sent)
                        matched_index.add(sent[0].i)
        
        # ======= 3. 输出 =======
        if len(matched_sents) == 0:
            return None, None
        else:
            return matched_sents, srchid2freq


if __name__ == "__main__":
    
    # lemmas = "shift revision test reform progress change improvement experiment".split()
    # query_list = []
    # for lemma in lemmas:
    #     if lemma == "union":
    #         query_list.append(Query(lemma=lemma, pos="NOUN"))
    #     elif lemma == "united":
    #         query_list.append(Query(lemma=lemma, pos="ADJ"))
    #     else:
    #         query_list.append(Query(lemma=lemma))
    
    srcher = LingPatternSearcher()
    