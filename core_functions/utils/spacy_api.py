## encoding: utf-8
'''
Created on Jun 29, 2020

@author: arthur
'''
import os, codecs
import json
import spacy
from spacy.tokens import Doc, Token


# QCoreApplication.translate 允许你在非 QObject 类中标记和翻译字符串（静态翻译方法）
from PySide6.QtCore import QCoreApplication


from .common import resource_path
from .common import DEFAULT_MODELS

MINIMUM_WORD_SIMILARITY = -1.0

# https://spacy.io/usage/linguistic-features#native-tokenizer-additions
from spacy.lang.char_classes import ALPHA, ALPHA_LOWER, ALPHA_UPPER
from spacy.lang.char_classes import CONCAT_QUOTES, LIST_ELLIPSES, LIST_ICONS
from spacy.util import compile_infix_regex

# Modify tokenizer infix patterns (修改spaCy的分词规则中的infixes-词中分隔符)
infixes = (
    LIST_ELLIPSES
    + LIST_ICONS
    + [
        r"(?<=[0-9])[+\-\*^](?=[0-9-])",
        r"(?<=[{al}{q}])\.(?=[{au}{q}])".format(
            al=ALPHA_LOWER, au=ALPHA_UPPER, q=CONCAT_QUOTES
        ),
        r"(?<=[{a}]),(?=[{a}])".format(a=ALPHA),
        # ✅ Commented out regex that splits on hyphens between letters: 意味着：不再切开 “co-operate” 这种带连字符的词
        # r"(?<=[{a}])(?:{h})(?=[{a}])".format(a=ALPHA, h=HYPHENS),
        r"(?<=[{a}0-9])[:<>=/](?=[{a}])".format(a=ALPHA),
    ]
)
infix_re = compile_infix_regex(infixes)


class SpacyAPI(object):

    def __init__(self, lang="zh", use_gpu=False):
        '''
        The spaCy models can be constantly updated to keep pace with the state of the art technique. 
        @param lang: could be in ["zh", "en", "fr", "de", "ja].
        '''
        self.lang = lang

        self.model_dir = self._get_prefered_model_path()

        if not self.model_dir:
            self.nlp = None
            raise RuntimeError(f"⚠️ 未能定位到语言 [{lang}] 的 spaCy 模型，请前往“设置”页面检查模型目录配置。")

        else:
            # load the model ----------
            self.use_gpu = use_gpu
            # import torch
            if self.use_gpu:# and torch.cuda.is_available():
                spacy.require_gpu(gpu_id=0)
            else:
                spacy.require_cpu()
            
            self.nlp = spacy.load(self.model_dir)
            self.nlp.add_pipe('sentencizer')
            self.nlp.max_length = 1500000
            # 自定义 infix
            self.nlp.tokenizer.infix_finditer = infix_re.finditer
            print(f"✅ Using model {self.model_dir}")
        
    def _get_prefered_model_path(self):
        # 根据程序配置文件，读取模型目录及偏好模型。
        with open(resource_path("ex", "settings.json"), "r", encoding="utf-8") as f:
            cfg = json.load(f)
            model_path = cfg.get("model_paths", {}).get(self.lang)
        
        # 1. 优先尝试使用自定义路径
        if model_path and os.path.isdir(model_path):
            return model_path

        # 2. 自定义路径无效，则使用内置 fallback 路径
        # 假设你打包时把模型放在了内部的 models/zh_core_web_sm 目录下
        model_name = DEFAULT_MODELS.get(self.lang)
        model_path = resource_path("in", "models", model_name) # 指向打包装后的临时解压目录/_MEIPASS/models/... 或者开发环境下的 ./models/...
        # 额外说明：spaCy 加载本地模型时，有时需要指向解压后的具体文件夹，有时如果该文件夹是一个 package 结构（包含 __init__.py），也可以直接 load。最稳妥的方式是指向包含 config.cfg 的那一层目录。
        return model_path
        
    def pipeline(self, txt, merge_noun_chunks=False, merge_entities=False, parsing=True, reporter=None): 
        '''
        Use this function to fully analyze a text.

        Args:
            reporter (ProgressReporter): 可多层下传进度，用于进度回调/Qt 信号。
        '''
        if parsing == False:
            self.nlp.disable_pipe("parser")
            self.nlp.disable_pipe("ner")
            self.nlp.enable_pipe("sentencizer")

        if self.lang == "zh":
            if merge_entities:
                if "merge_entities" not in self.nlp.component_names:
                    self.nlp.add_pipe("merge_entities")
                self.nlp.enable_pipe("merge_entities")
        else:
            if merge_noun_chunks:
                if "merge_noun_chunks" not in self.nlp.component_names:
                    self.nlp.add_pipe("merge_noun_chunks")
                self.nlp.enable_pipe("merge_noun_chunks")
            else:
                if "merge_noun_chunks" in self.nlp.component_names:
                    self.nlp.disable_pipe("merge_noun_chunks")
            
            if merge_entities:
                if "merge_entities" not in self.nlp.component_names:
                    self.nlp.add_pipe("merge_entities")
                self.nlp.enable_pipe("merge_entities")
            else:
                if "merge_entities" in self.nlp.component_names:
                    self.nlp.disable_pipe("merge_entities")
        
        # 对大文本按照 max_length 进行分块
        if txt == "":
            txts = [""]
        else:
            txts = []
            while len(txt) > 0:
                max_length = 100000
                max_len_offset = min(len(txt), max_length)
                txts.append( txt[:max_len_offset] )
                if max_len_offset == len(txt): break
                else: txt = txt[max_len_offset:]

        # 开始正式处理
        docs = []
        Token.set_extension("lemma_lower", getter=lambda t: t.lemma_.lower(), force=True)

        total = len(txts)
        for i, txt_part in enumerate(txts, start=1):
            # 汇报进度
            if reporter:
                pct = int(i /total *100)
                reporter.report(pct, QCoreApplication.translate("SpacyAPI", "语料解析中[{}/{}]……").format(i, total))

            doc = self.nlp(txt_part)
            if doc != None:
                docs.append(doc)
        
        return Doc.from_docs(docs)
            
    def obtain_word_embeddings(self, words):
        '''
        Obtain embedding for one word, or a short phrase
        @param words: A string that contains one or more word, separated with space 
        @param return: a vector 
        '''
        self.nlp.enable_pipe('tok2vec')
        processed = self.nlp(words)
        return processed.tensor
    
    def obtain_sentence_embeddings(self, sentences):
        '''
        This function obtains vectors for sentences
        @param sentences: a string consisting of sentences.
        @return: a list of tuples, each of the form (sentence, vector)
        '''
        doc = self.pipeline(sentences)
        result = []
        for s in doc.sents:
            result.append(s.text, s.vector)
        return result
    
    def lemmatize(self, textStr):
        '''
        @return return a list of sentences, each a token list
        '''
        if self.lang != "en":
            print("Chinese does not require lemmatization.")
            return textStr
        else:
            self.nlp.disable_pipe("parser")
            self.nlp.disable_pipe("ner")
            doc = self.nlp(textStr)
            self.nlp.enable_pipe("parser")
            self.nlp.enable_pipe("ner")
            return doc
        
    def ready_tokenize(self):
        self.nlp.disable_pipe("parser")
        self.nlp.disable_pipe("ner")
        
    def restore_tokenize(self):
        self.nlp.enable_pipe("parser")
        self.nlp.enable_pipe("ner")
            
    def tokenize(self,textStr):
        '''
        This function performs tokenization on text string.
        @param textStr: text string to be tokenized
        @return return a list of sentences, each a token list 
        '''
        doc = self.nlp(textStr)
        
        return doc
    
    def part_of_speech_tag(self,textStr):
        return self.tokenize(textStr)
    
    def dependency_parse_to_conll(self, textStr, style=4):
        '''
        This function takes a textStr that contains multiple sentences and 
        return a parse tree in style 4 conll format, namely word, pos_tag, head, dependency relation.
        @param textStr: A string contains one or more sentences
        @return: Return style 4 conll format 
        '''
        self.nlp.enable_pipe('parser')
        self.nlp.enable_pipe('ner')
        parse_result = ""
        doc = self.nlp(textStr)
        for sent in doc.sents:
            if style == 4:
                tempStr = self.derive_conll_4_style(sent)
            elif style == 7:
                tempStr = self.derive_conll_7_style(sent, doc)
            else:
                tempStr = self.derive_conll_4_style(sent)
            parse_result += (tempStr + "\n\n")
        self.nlp.disable_pipe('parser')
        self.nlp.disable_pipe('ner')
        return parse_result
    
    def derive_conll_4_style(self, sent):
        ''' Return 4 style conll format: word,postag, head_index, and word_dep_        
        '''
        tempStr = ""
        for word in sent:
            if word.head == word: head_idx = 0
            else: head_idx = word.head.i - sent[0].i + 1    
            tempStr += u"{:<30}{:<30}{:<30}{}\n".format(
                            word.text,
                            word.tag_,
                            head_idx,
                            word.dep_
            )
        
    def derive_conll_7_style(self, sent, doc):
        ''' Return seven style conll format: index, word, lemma, pos_tag, entity_tag, head_index, and depenency_relation
        '''
        rsltStr =""
        for w in sent:
                if w.head == w: head_idx = 0
                else: head_idx = w.head.i - sent[0].i + 1                
                if w.lemma_: lemma = w.lemma_
                else: lemma = "-"

                rsltStr += u"{:<30}{:<30}{:<30}{:<30}{:<30}{:<30}{}\n".format(w.i+1,
                                                                                      w.text, 
                                                                                      lemma,
                                                                                      w.tag_,
                                                                                      w.ent_iob_, 
                                                                                      head_idx,
                                                                                      w.dep_)
        return rsltStr
    
    def detectSentenceBoundary(self, docStr):
        '''
        @param docStr: A string of sentences
        '''
        sents = []
        tokenlists = self.tokenize(docStr)
        for l in tokenlists:
            sents.append( " ".join(l) )
        return sents
    
    def parseFileToConll(self, input_path, output_path, style=7):
        try:
            ops = codecs.open(output_path, "w", encoding='utf-8')
            with codecs.open(input_path, encoding="utf-8", errors="ignore") as ips:
                text = ips.read()
                rsltText =  self.dependency_parse_to_conll(text, style=style)
                ops.write(rsltText)
            ops.close()
        except Exception as e:
            print(e)
    
    def getWordVector(self, w):
        # spaCy transformer 模型
        if "trf" in self.model_dir:
            # transformer 模型没有静态 vocab 向量，需通过管线取
            doc = self.nlp(w)
            trf = getattr(doc._, "trf_data", None)
            if trf is None or not trf.tensors:
                return None
            # 取最后一层隐藏状态
            tensor = trf.tensors[-1]           # shape: (1, seq_len, hidden)
            # 通常第 1 个 token 是 CLS，第 -1 个是 SEP，可取中间 token 平均池化
            # 或简单平均全部 token（除去特殊标记）
            arr = tensor[0].detach().cpu().numpy()
            if arr.shape[0] > 2:
                arr = arr[1:-1]  # 去掉 [CLS] 和 [SEP]
            vec = arr.mean(axis=0)             # (hidden_size,)
            return vec
        
        # 普通静态词向量模型
        else:
            return self.nlp.vocab[w].vector

    def vector_based_word_similarity(self,w1,w2):
        if w1 in self.nlp.vocab and w2 in self.nlp.vocab:
            return self.nlp.vocab[w1].similarity(self.nlp.vocab[w2])
        else:
            return MINIMUM_WORD_SIMILARITY



if __name__== "__main__":
    texts_en = [
        "A 76-year-old woman who was declared dead at a hospital in Ecuador was found to be alive and knocking on her coffin during her own wake in the city of Babahoyo.",
        "The man recording the video later asked the name of the woman, to which someone in the room replied: \“Bella Yolanda.\”",
        "The gunfire was reported in the 2000 block of Market Street, police said, near the intersection with 20th Street.",
        "The US aviation system is set for a record-breaking summer, with the Transportation Security Administration already reporting passenger volumes greater than pre-pandemic levels during the Memorial Day weekend.",
        "May’s closely watched Consumer Price Index showed Tuesday that inflation has been cut by more than half from last year’s peak."
        ]
    SPACY_API_EN = SpacyAPI(lang="en")
    for test_str in texts_en:
        doc = SPACY_API_EN.pipeline(test_str, merge_noun_chunks=False, merge_entities=False)
        print(doc)
    
    # texts_chn = [
    #     "因为春娥吃得少，校食堂还对她特殊定价。",
    #     "整整一个冬天，我都在体验着、感悟着。",
    #     "这种感觉我曾经体验过。",
    #     "这几年庄稼人家饭也没法吃得饱。"
    #     ]
    # SPACY_API_ZH = SpacyAPI(lang="zh")
    # for test_str in texts_chn:
    #     doc = SPACY_API_ZH.pipeline(test_str, merge_noun_chunks=False, merge_entities=False)
    #     print(doc)
    
