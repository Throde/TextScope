'''
Updated on Oct 18, 2025

@author: arthur, Liu Daohuan
'''
## encoding: UTF-8
import os, logging

from collections import namedtuple
from nltk.metrics.association import BigramAssocMeasures
# from scipy.stats import fisher_exact
import dill as pickle
from collections import defaultdict
import math
import numpy as np
# from sklearn.preprocessing import FunctionTransformer
# from sklearn.metrics.pairwise import euclidean_distances

from .utils.spacy_api import SpacyAPI
from .utils.corpus_readers import read_data
from .utils.lang_ptn_searcher import LingPatternSearcher, Query

import matplotlib
matplotlib.use("Agg") # 把后端切到 Agg（离屏渲染），避免在子线程启动 GUI
import matplotlib.pyplot as plt
import matplotlib.colors as mcolors

# 可视化相关
from adjustText import adjust_text
from .textalloc import allocate
from typing import Any, Dict

from .utils.progress_reporter import ProgressReporter

# QCoreApplication.translate 允许你在非 QObject 类中标记和翻译字符串（静态翻译方法）
from PySide6.QtCore import QCoreApplication


# 全局语料缓存
# 用于在不同 Worker 之间共享已加载的语料，避免 KWIC 重复加载
# 结构: {"path": "c:/data/corpus.txt", "doc": spacy_doc_object, "case_sensitive": True}
_CURRENT_CORPUS_CACHE = {
    "path": None,
    "doc": None,
    "case_sensitive": None
}


# ==========================================
# Firthian Collocation获取器
# ==========================================
class CollocationRetriever():
    
    tagset = {
        "verb": set(["VB", "VBD", "VBG", "VBN", "VBP", "VBZ", "VERB"]),
        "noun": set(["NN", "NNS", "NNP", "NNPS", "NOUN"]),
        "adj": set(["JJ", "JJR", "JJS", "ADJ"]),
        "adv": set(["ADV"]),
        "propn": set(["PROPN"]),
        "content": set(["VERB", "NOUN", "ADJ", "ADV", "PROPN"]),
        "function": set(["ADP","AUX","CCONJ","DET","NUM","PART","PRON","SCONJ","FUNCT","SYM","X"]),
    }
    
    def __init__(self, 
                 lang: str="zh", 
                 metric: str="PMI", 
                 winsize: tuple=(5,5), 
                 case_sensitive: bool=True, 
                 use_lemma: bool=False, 
                 min_cofreq_percentage: float=0.0025, 
                 coll_pos_filter: list=[]):
        self.lang = lang
        # 初始化语言模型
        self.spacy_api = SpacyAPI(self.lang) # 若模型缺失，需要前往SpaCy官网下载安装
        self.doc = None # 保存语料

        self.metric = metric
        
        self.left_window_size = winsize[0]
        self.right_window_size = winsize[1]
        
        self.case_sensitive = case_sensitive
        self.use_lemma = use_lemma

        # 搭配词 requirements
        # 搭配词的词性：如果参数为空表，则表示全部包含（不作限定）
        self.valid_coll_pos = set()
        for pos, tags in self.tagset.items():
            if pos in coll_pos_filter:
                self.valid_coll_pos.update(tags)
        # self.min_cofreq_percentage is used to filter out insignificant collocates by way of co-occurrence frequency. E.g., a collocate is considered insignificant if it occurs less than 2 times in every 1000 node instances. More precisely, the filter is co-freq/target-freq.
        self.min_cofreq_percentage = min_cofreq_percentage

    ############################################################
    ## Deal with individual file
    def collect_word_frequency(self, src_path, save_path=""):
        """Collect word frequency of all words for a corpus defined by pickled DocBin objects (ref. spacy) in the source file/directory and save to the file (save_path). The frequency contains the following inforation types:
           (1) wordform frequency
           (2) lemma frequency
           (3) word-pos frequency

        Args:
            src_path (str): source directory with DocBin objects
            save_path: path to pickled word frequency data.
        """
        
        src_dir = os.path.dirname(src_path)        
        if save_path == "":
            if self.case_sensitive:
                output_path = os.path.join(src_dir, os.path.basename(src_path) + ".freq_case_sensitive.pkl")
            else:
                output_path = os.path.join(src_dir, os.path.basename(src_path) + ".freq_case_insensitive.pkl")
        else:
            output_path = save_path
            
        N = 0
        
        if os.path.exists(output_path):
            with open(output_path, "rb") as ips:
                self.word_freq, self.lemma_freq, self.word_pos_freq = pickle.load(ips)
        else:
            word_freq = defaultdict(int)
            lemma_freq = defaultdict(int)
            word_pos_freq = defaultdict(int)
            
            # 接下来统计上面三个dict
            if not self.doc:
                print("Warning: Corpus not loaded yet.")

            for t in self.doc:
                wd_pos = f"{t.text}/{t.pos_}" if self.case_sensitive else f"{t.text.lower()}/{t.pos_}"
                word_pos_freq[wd_pos] += 1
                lemma_pos = f"{t.lemma_}/{t.pos_}" if self.case_sensitive else f"{t.lemma_.lower()}/{t.pos_}"
                lemma_freq[lemma_pos] += 1
                if self.case_sensitive: word_freq[t.text] += 1  
                else: word_freq[t.text.lower()] += 1
            N += len(self.doc)
            
            # remove low frequency words, lemmas and word-poses
            new_word_freq = defaultdict()
            for w, f in word_freq.items():
                if f <= 1: continue
                else: new_word_freq[w] = f
            word_freq = new_word_freq            
            word_freq["BIG_N"] = N
            
            new_word_freq = defaultdict()
            for w, f in lemma_freq.items():
                if f <= 1: continue
                else: new_word_freq[w] = f
            lemma_freq = new_word_freq            
            lemma_freq["BIG_N"] = N
            
            new_word_freq = defaultdict()
            for w, f in word_pos_freq.items():
                if f <= 1: continue
                else: new_word_freq[w] = f
            word_pos_freq = new_word_freq            
            word_pos_freq["BIG_N"] = N
            
            # save file
            with open(output_path, "wb") as ops:
                pickle.dump([word_freq, lemma_freq, word_pos_freq],ops)
                
            self.word_freq = word_freq # e.g. {'小火': 44, ...}
            self.lemma_freq = lemma_freq # e.g. {'/NOUN': 807, ...} (中文无lemma，相同词性的均会累加在一起)
            self.word_pos_freq = word_pos_freq # e.g. {'小火/NOUN': 38, ...}
        
    def get_typed_word_freq(self, type: str, wd: str, pos: str=""):
        """Get typed word frequency

        Args:
            type (_type_): one of the following three types: wordform, lemma_pos, word_pos
            word (str): _description_
            pos (str, optional): _description_. Defaults to "".
        """
        if type == "wordform":
            if wd not in self.word_freq: return 1
            else: return self.word_freq[wd]
        elif type == "lemma_pos":
            lemma_pos = f"{wd}/{pos}"
            if lemma_pos not in self.lemma_freq: return 1
            else: return self.lemma_freq[lemma_pos]
        elif type == "word_pos":
            word_pos = f"{wd}/{pos}"
            if word_pos not in self.word_pos_freq: return 1
            else: return self.word_pos_freq[word_pos]
        else:
            raise "Frequency search type should be specified."
    
    def get_node_word_freq(self, wd: str, pos: str=""):
        # 节点词特殊之处：必须为lemma，但中文又要去word_freq找
        srch_form = wd if pos == "" else f"{wd}/{pos}"
        if self.lang in ["en", "fr", "de", "ja"]:
            if srch_form in self.lemma_freq:
                return self.lemma_freq[srch_form]
            elif srch_form in self.word_freq: # fallback
                return self.word_freq[srch_form]
            else: return 1
        elif self.lang == "zh":
            if srch_form in self.word_freq:
                return self.word_freq[srch_form]
            else:
                return 1
    
    ## --------------------------- functions for collocation frequency ---------------------##
    ##
    def obtain_collocation_distribution(self, tgtWord: str, pos_list: list, reporter: ProgressReporter = None):
        """Collect frequency data from self.doc.

        Args:
            tgtWord (str): node word
            pos_list (list): list of part-of-speech of the node word.

        Returns:
            _type_: a list of qudruples containing collocates' frequencies and positions at both sides. 
            The data structure is as follows:
            leftfd:         dictionary, {bigram:frequency}
            left_pstns:     dictionary, {bigram:average distance}
            rightfd:        dictionary, {bigram:frequency}
            right_pstns:    dictionary, {bigram:average distance}
        """
        if not reporter:
            reporter = ProgressReporter(lambda *_: None)  # 构造一个安静的默认汇聚器，以兼容用户不传的情况
        
        # 读取数据
        reporter.report(0, QCoreApplication.translate("CollocationRetriever", "检索语料……"))
        if not self.doc:
            print("Warning: Corpus not loaded yet.")
        
        # 构造 queries
        if self.lang in ["en", "fr", "de", "ja"]: # 有 lemma 语言
            if len(pos_list)>0:
                queries = [Query(lemma=tgtWord, pos=pos) for pos in pos_list]
            else:
                queries = [Query(lemma=tgtWord)]
        else: # 无 lemma 语言
            if len(pos_list)>0:
                queries = [Query(wordform=tgtWord, pos=pos) for pos in pos_list]
            else:
                queries = [Query(wordform=tgtWord)]
        sents, _ = LingPatternSearcher.search_in_spacy_doc(self.doc, 
                                                           self.spacy_api, 
                                                           queries,
                                                           reporter=reporter.child(0,80))

        reporter.report(80, QCoreApplication.translate("CollocationRetriever", "收集搭配信息……"))
        leftBiGrams = []
        rightBiGrams = []
        if sents != None:
            # Collect left side and right side information
            leftBiGrams, rightBiGrams = self.collect_neighbors(sents, tgtWord, pos_list, reporter=reporter.child(80,90))

        reporter.report(90, QCoreApplication.translate("CollocationRetriever", "收集搭配信息……"))
        leftfd, left_pstns = self.getCoOccurrenceFreq_(leftBiGrams, left=True)
        reporter.report(95, QCoreApplication.translate("CollocationRetriever", "收集搭配信息……"))
        rightfd, right_pstns = self.getCoOccurrenceFreq_(rightBiGrams, left=False)
        
        return leftfd, left_pstns, rightfd, right_pstns
    
    def getCoOccurrenceFreq_(self, biGrams, left=True):
        fd = defaultdict(int)
        pstns = defaultdict(list)
        for bigram, pstn in biGrams:
            fd[bigram] += 1
            pstns[bigram].append(pstn)
        
        ave_pstns = defaultdict(float)
        for bigram, pstn_list in pstns.items():
            if left:
                ave_pstns[bigram[0]] = sum(pstn_list) / len(pstn_list)
            else:
                ave_pstns[bigram[2]] = sum(pstn_list) / len(pstn_list)
            
        return fd, ave_pstns
    
    def collect_neighbors(self, sents: list, tgtWord: str, pos_list: list, reporter: ProgressReporter = None):
        """_summary_

        Args:
            sents (_type_): list of sentences in spacy-format.
            tgtWord (str): node word.
            pos_list (list): list of part-of-speech of the node word.

        Returns:
            _type_: bigram information for left side colloccates and right side collocates.
            For the leftbigrams, the data structure is 
                (
                    (left-collocate wordform, left-collocate part-of-speech,
                     node wordform, node part-of-speech),
                    distance
                )
            For the rightbigrams, the data structure is
                (
                    (node wordform, node part-of-speech,
                     right-collocate wordform, right-collocate part-of-speech),
                    distance
                )
        """
        if not reporter:
            reporter = ProgressReporter(lambda *_: None)  # 构造一个安静的默认汇聚器，以兼容用户不传的情况

        LeftBiGrams = []
        RightBiGrams = []
        
        for sentence in reporter.wrap(sents):
            first_word_i = sentence[0].i
            last_word_i = sentence[-1].i
            for t in sentence:
                # 找到句中的节点词
                if self._is_valid_node_word(t, tgtWord, pos_list):
                    tgt_pstn = t.i
                    startIndex = max(first_word_i, tgt_pstn-self.left_window_size)
                    endIndex = min(last_word_i, tgt_pstn + self.right_window_size + 1)

                    # 获取节点词的形式 (用于存储在 bigram 中作为参照)
                    # 节点词通常建议保持一种稳定形式，这里原代码是用 lemma 的，保持不变
                    node_form = self._get_lemma(t).lower()

                    if startIndex != tgt_pstn:
                        # 收集左侧搭配信息
                        for i in range(startIndex, tgt_pstn):                            
                            left_token = sentence[ i - first_word_i ]
                            if self._is_wanted_pos(left_token.pos_):
                                l_wf, l_lemma, l_pos = self._get_wf_lemma_pos(left_token)
                                # 根据 use_lemma 决定使用哪种形式
                                target_form = l_lemma if self.use_lemma else l_wf
                                LeftBiGrams.append( ((target_form, l_pos, node_form, t.pos_), tgt_pstn-i) )
                    if endIndex != tgt_pstn:
                        # 收集右侧搭配信息
                        for i in range(tgt_pstn+1, endIndex):
                            right_token = sentence[ i - first_word_i]
                            if self._is_wanted_pos(right_token.pos_):
                                r_wf, r_lemma, r_pos = self._get_wf_lemma_pos(right_token)
                                # 根据 use_lemma 决定使用哪种形式
                                target_form = r_lemma if self.use_lemma else r_wf
                                RightBiGrams.append( ((node_form, t.pos_, target_form, r_pos), i-tgt_pstn) )
                            
        return LeftBiGrams, RightBiGrams
    
    def _is_valid_node_word(self, token, tgtWord: str, pos_list: list):
        # The node is required to be the lemma and its part-of-speech should be given
        lem = self._get_lemma(token)
        satisfied = (lem == tgtWord or lem.lower() == tgtWord.lower())
        if satisfied:
            if len(pos_list)>0 and token.pos_ not in pos_list: return False
        return satisfied
    
    def _is_wanted_pos(self, pos_tag: str):
        if len(self.valid_coll_pos) == 0 or pos_tag in self.valid_coll_pos:
            return True
        else:
            return False

    def _get_wf_lemma_pos(self, token):
        wf = token.text
        lemma = self._get_lemma(token)
        pos = token.pos_
        if not self.case_sensitive:
            wf = wf.lower()
            lemma = lemma.lower()
        return wf, lemma, pos
    
    def _get_lemma(self, token):
        # 返回给定 token 的词形
        if self.lang in ["en", "fr", "de", "ja"]:
            return token.lemma_
        elif self.lang == "zh":
            # Chinese spacy_tok does not has .lemma_ item, use .text instead.
            return token.text
        
    ##----------------------functions for association strength computation -------------------
    ##
    def get_collocation_data(self, fd, ave_pstns, tgt_freq, N, left=True):
        collocates = []
        strength_list = []
        pstns = []
        pos_list = []
        ## Filter out those collocates that are exceptional in frequency or other reasons.
        # not_wanted_collocates = "Madly Piggys Jacks re".split()
        for bigram, co_freq in fd.items():
            if co_freq/tgt_freq > self.min_cofreq_percentage:
                if left:
                    collocate = bigram[0]
                    collocate_pos = bigram[1]
                else:
                    collocate = bigram[2]
                    collocate_pos = bigram[3]
                
                # if collocate in not_wanted_collocates: continue
                
                # 【修改点】：如果启用了 lemma，就要查 lemma_pos 的频率表，否则查 word_pos 的表
                # 注意：collect_word_frequency 中已经生成了 lemma_freq 和 word_pos_freq
                freq_type = "lemma_pos" if self.use_lemma else "word_pos"
                collocate_freq = self.get_typed_word_freq(freq_type, collocate, collocate_pos)

                strength = self.getAssociationStrength(tgt_freq, collocate_freq, co_freq, N)
                pstn = ave_pstns[collocate]
                
                if strength <= 0: continue
                
                collocates.append(collocate)
                strength_list.append(strength)
                if left: pstns.append(-pstn)
                else: pstns.append(pstn)
                pos_list.append(collocate_pos)
                
        #strength_list = self.normalize(np.asarray(strength_list))
                
        return collocates, strength_list, pstns, pos_list
    
    def setMetric(self, metric_name):
        self.metric = metric_name
    
    def getAssociationStrength(self, tgt_freq, collocate_freq, co_freq,  N):
        '''
        @param tgt_freqs: list of frequency of target words
        @param collocate_freqs: list of frequency of collocates
        @param cooccur_freqs: list of cooccurrence frequency of targets and collocates
        @param N: token number sum
        
        --------------------------------------
              | u        |       ~u    |
        --------------------------------------
          v   | n_ii     |      n_oi   | n_xi
        --------------------------------------
          ~v  | n_io     |      n_oo   | 
        --------------------------------------
                n_ix     |             | n_xx
        '''
        try:
            n_ii = co_freq
            n_io = tgt_freq-n_ii
            n_ix = tgt_freq
            n_xi = collocate_freq
            n_oi = collocate_freq-n_ii
            n_oo = N-n_ii
            n_xx = N
            
            e_ii = tgt_freq * collocate_freq / N
            
            if self.metric == "Phi-square-test":
                return BigramAssocMeasures.phi_sq(n_ii, (n_ix, n_xi), n_xx)            
            elif self.metric == "Chi-square-test":
                return BigramAssocMeasures.chi_sq(n_ii, (n_ix, n_xi), n_xx)
            elif self.metric == "t-test":
                return BigramAssocMeasures.student_t(n_ii, (n_ix, n_xi), n_xx)
            elif self.metric == "Dice":
                return BigramAssocMeasures.dice(n_ii, (n_ix, n_xi), n_xx)
            elif self.metric == "MI-like-3":
                return BigramAssocMeasures.mi_like(n_ii, (n_ix, n_xi), n_xx)
            elif self.metric == "PMI":
                return BigramAssocMeasures.pmi(n_ii, (n_xi, n_ix), n_xx)
            elif self.metric == "Log-likelihood-ratio":
                return BigramAssocMeasures.likelihood_ratio(n_ii, (n_ix, n_xi), n_xx)
            elif self.metric == "Poisson-stirling":
                return BigramAssocMeasures.poisson_stirling(n_ii, (n_ix, n_xi), n_xx)
            elif self.metric == "Jaccard":
                return BigramAssocMeasures.jaccard(n_ii, (n_ix, n_xi), n_xx)
            elif self.metric == "Local_MI":
                return self.local_mutual_information(n_ii, e_ii)
            elif self.metric == "ΔP":
                return self.delta_p_conditioned_on_node(n_ii, n_xi, n_io, n_oo)
            elif self.metric == "Minimum-sensitivity":
                return self.minimum_sensitivity(n_ii, n_xi, n_ix)
            elif self.metric == "Fisher-exact-test":
                odd_ratio, p_value = self.fisher_exact([[n_ii, n_oi],[n_io, n_oo]], alternative="less")
                return p_value
            else:
                logging.error("Association measure not defined!")
                return 0
            
        except Exception as e:
            print("{}: {}".format(e, self.metric))
            if self.metric == "fisher":
                return 0
            else:
                return 0
            
    def local_mutual_information(self, n_ii, e_ii):
        """Local mutual information by Gueguen et al (2014)

        Args:
            n_ii (_type_): _description_
            e_ii (_type_): _description_

        Returns:
            _type_: _description_
        """
        return n_ii * math.log ( n_ii / e_ii)
    
    def delta_p_conditioned_on_node(self, n_ii, n_xi, n_io, n_oo):
        ## ΔP = p (outcome | cue = present) − p (outcome | cue = absent)
        ## Gries (2013)
        return (n_ii / n_xi) - (n_io / n_oo)
    
    def minimum_sensitivity(self, n_ii, r1, c1):
        return min( n_ii/r1, n_ii/c1 )
    
    def fisher_exact(self, table, alternative='two-sided'):
        # Note: a lite function revised from scipy.stats.fisher_exact to realize SciPy-free.
        """Perform a Fisher exact test on a 2x2 contingency table.

        The null hypothesis is that the true odds ratio of the populations
        underlying the observations is one, and the observations were sampled
        from these populations under a condition: the marginals of the
        resulting table must equal those of the observed table. The statistic
        returned is the unconditional maximum likelihood estimate of the odds
        ratio, and the p-value is the probability under the null hypothesis of
        obtaining a table at least as extreme as the one that was actually
        observed. There are other possible choices of statistic and two-sided
        p-value definition associated with Fisher's exact test; please see the
        Notes for more information.

        Parameters
        ----------
        table : array_like of ints
            A 2x2 contingency table.  Elements must be non-negative integers.
        alternative : {'two-sided', 'less', 'greater'}, optional
            Defines the alternative hypothesis.
            The following options are available (default is 'two-sided'):

            * 'two-sided': the odds ratio of the underlying population is not one
            * 'less': the odds ratio of the underlying population is less than one
            * 'greater': the odds ratio of the underlying population is greater
            than one

            See the Notes for more details.

        Returns
        -------
        res : SignificanceResult
            An object containing attributes:

            statistic : float
                This is the prior odds ratio, not a posterior estimate.
            pvalue : float
                The probability under the null hypothesis of obtaining a
                table at least as extreme as the one that was actually observed.

        See Also
        --------
        chi2_contingency : Chi-square test of independence of variables in a
            contingency table.  This can be used as an alternative to
            `fisher_exact` when the numbers in the table are large.
        contingency.odds_ratio : Compute the odds ratio (sample or conditional
            MLE) for a 2x2 contingency table.
        barnard_exact : Barnard's exact test, which is a more powerful alternative
            than Fisher's exact test for 2x2 contingency tables.
        boschloo_exact : Boschloo's exact test, which is a more powerful
            alternative than Fisher's exact test for 2x2 contingency tables.

        Notes
        -----
        *Null hypothesis and p-values*

        The null hypothesis is that the true odds ratio of the populations
        underlying the observations is one, and the observations were sampled at
        random from these populations under a condition: the marginals of the
        resulting table must equal those of the observed table. Equivalently,
        the null hypothesis is that the input table is from the hypergeometric
        distribution with parameters (as used in `hypergeom`)
        ``M = a + b + c + d``, ``n = a + b`` and ``N = a + c``, where the
        input table is ``[[a, b], [c, d]]``.  This distribution has support
        ``max(0, N + n - M) <= x <= min(N, n)``, or, in terms of the values
        in the input table, ``min(0, a - d) <= x <= a + min(b, c)``.  ``x``
        can be interpreted as the upper-left element of a 2x2 table, so the
        tables in the distribution have form::

            [  x           n - x     ]
            [N - x    M - (n + N) + x]

        For example, if::

            table = [6  2]
                    [1  4]

        then the support is ``2 <= x <= 7``, and the tables in the distribution
        are::

            [2 6]   [3 5]   [4 4]   [5 3]   [6 2]  [7 1]
            [5 0]   [4 1]   [3 2]   [2 3]   [1 4]  [0 5]

        The probability of each table is given by the hypergeometric distribution
        ``hypergeom.pmf(x, M, n, N)``.  For this example, these are (rounded to
        three significant digits)::

            x       2      3      4      5       6        7
            p  0.0163  0.163  0.408  0.326  0.0816  0.00466

        These can be computed with::

            >>> import numpy as np
            >>> from scipy.stats import hypergeom
            >>> table = np.array([[6, 2], [1, 4]])
            >>> M = table.sum()
            >>> n = table[0].sum()
            >>> N = table[:, 0].sum()
            >>> start, end = hypergeom.support(M, n, N)
            >>> hypergeom.pmf(np.arange(start, end+1), M, n, N)
            array([0.01631702, 0.16317016, 0.40792541, 0.32634033, 0.08158508,
                0.004662  ])

        The two-sided p-value is the probability that, under the null hypothesis,
        a random table would have a probability equal to or less than the
        probability of the input table.  For our example, the probability of
        the input table (where ``x = 6``) is 0.0816.  The x values where the
        probability does not exceed this are 2, 6 and 7, so the two-sided p-value
        is ``0.0163 + 0.0816 + 0.00466 ~= 0.10256``::

            >>> from scipy.stats import fisher_exact
            >>> res = fisher_exact(table, alternative='two-sided')
            >>> res.pvalue
            0.10256410256410257

        The one-sided p-value for ``alternative='greater'`` is the probability
        that a random table has ``x >= a``, which in our example is ``x >= 6``,
        or ``0.0816 + 0.00466 ~= 0.08626``::

            >>> res = fisher_exact(table, alternative='greater')
            >>> res.pvalue
            0.08624708624708627

        This is equivalent to computing the survival function of the
        distribution at ``x = 5`` (one less than ``x`` from the input table,
        because we want to include the probability of ``x = 6`` in the sum)::

            >>> hypergeom.sf(5, M, n, N)
            0.08624708624708627

        For ``alternative='less'``, the one-sided p-value is the probability
        that a random table has ``x <= a``, (i.e. ``x <= 6`` in our example),
        or ``0.0163 + 0.163 + 0.408 + 0.326 + 0.0816 ~= 0.9949``::

            >>> res = fisher_exact(table, alternative='less')
            >>> res.pvalue
            0.9953379953379957

        This is equivalent to computing the cumulative distribution function
        of the distribution at ``x = 6``:

            >>> hypergeom.cdf(6, M, n, N)
            0.9953379953379957

        *Odds ratio*

        The calculated odds ratio is different from the value computed by the
        R function ``fisher.test``.  This implementation returns the "sample"
        or "unconditional" maximum likelihood estimate, while ``fisher.test``
        in R uses the conditional maximum likelihood estimate.  To compute the
        conditional maximum likelihood estimate of the odds ratio, use
        `scipy.stats.contingency.odds_ratio`.

        References
        ----------
        .. [1] Fisher, Sir Ronald A, "The Design of Experiments:
            Mathematics of a Lady Tasting Tea." ISBN 978-0-486-41151-4, 1935.
        .. [2] "Fisher's exact test",
            https://en.wikipedia.org/wiki/Fisher's_exact_test
        .. [3] Emma V. Low et al. "Identifying the lowest effective dose of
            acetazolamide for the prophylaxis of acute mountain sickness:
            systematic review and meta-analysis."
            BMJ, 345, :doi:`10.1136/bmj.e6779`, 2012.

        Examples
        --------
        In [3]_, the effective dose of acetazolamide for the prophylaxis of acute
        mountain sickness was investigated. The study notably concluded:

            Acetazolamide 250 mg, 500 mg, and 750 mg daily were all efficacious for
            preventing acute mountain sickness. Acetazolamide 250 mg was the lowest
            effective dose with available evidence for this indication.

        The following table summarizes the results of the experiment in which
        some participants took a daily dose of acetazolamide 250 mg while others
        took a placebo.
        Cases of acute mountain sickness were recorded::

                                        Acetazolamide   Control/Placebo
            Acute mountain sickness            7           17
            No                                15            5


        Is there evidence that the acetazolamide 250 mg reduces the risk of
        acute mountain sickness?
        We begin by formulating a null hypothesis :math:`H_0`:

            The odds of experiencing acute mountain sickness are the same with
            the acetazolamide treatment as they are with placebo.

        Let's assess the plausibility of this hypothesis with
        Fisher's test.

        >>> from scipy.stats import fisher_exact
        >>> res = fisher_exact([[7, 17], [15, 5]], alternative='less')
        >>> res.statistic
        0.13725490196078433
        >>> res.pvalue
        0.0028841933752349743

        Using a significance level of 5%, we would reject the null hypothesis in
        favor of the alternative hypothesis: "The odds of experiencing acute
        mountain sickness with acetazolamide treatment are less than the odds of
        experiencing acute mountain sickness with placebo."

        .. note::

            Because the null distribution of Fisher's exact test is formed under
            the assumption that both row and column sums are fixed, the result of
            the test are conservative when applied to an experiment in which the
            row sums are not fixed.

            In this case, the column sums are fixed; there are 22 subjects in each
            group. But the number of cases of acute mountain sickness is not
            (and cannot be) fixed before conducting the experiment. It is a
            consequence.

            Boschloo's test does not depend on the assumption that the row sums
            are fixed, and consequently, it provides a more powerful test in this
            situation.

            >>> from scipy.stats import boschloo_exact
            >>> res = boschloo_exact([[7, 17], [15, 5]], alternative='less')
            >>> res.statistic
            0.0028841933752349743
            >>> res.pvalue
            0.0015141406667567101

            We verify that the p-value is less than with `fisher_exact`.

        """
        
        # --------- SignificanceResult 替代 _make_tuple_bunch ----------
        SignificanceResult = namedtuple('SignificanceResult', ['statistic', 'pvalue'])

        # int32 is not enough for the algorithm
        c = np.asarray(table, dtype=np.int64)
        if not c.shape == (2, 2):
            raise ValueError("The input `table` must be of shape (2, 2).")

        if np.any(c < 0):
            raise ValueError("All values in `table` must be nonnegative.")

        if 0 in c.sum(axis=0) or 0 in c.sum(axis=1):
            # If both values in a row or column are zero, the p-value is 1 and
            # the odds ratio is NaN.
            return SignificanceResult(np.nan, 1.0)

        if c[1, 0] > 0 and c[0, 1] > 0:
            oddsratio = c[0, 0] * c[1, 1] / (c[1, 0] * c[0, 1])
        else:
            oddsratio = np.inf

        # margins
        n1 = c[0, 0] + c[0, 1]
        n2 = c[1, 0] + c[1, 1]
        n = c[0, 0] + c[1, 0]
        M = n1 + n2

        # --- 内部定义超几何分布函数 ---
        def logchoose(n, k):
            if k < 0 or k > n:
                return -np.inf
            return math.lgamma(n + 1) - math.lgamma(k + 1) - math.lgamma(n - k + 1)

        def logpmf(k):
            return logchoose(n1, k) + logchoose(M - n1, n - k) - logchoose(M, n)

        def pmf(k):
            return math.exp(logpmf(k))

        def cdf(k):
            k_min = max(0, n - (M - n1))
            ks = np.arange(k_min, k + 1, dtype=int)
            logps = np.array([logpmf(xx) for xx in ks])
            return float(np.exp(np.logaddexp.reduce(logps)))

        def sf(k):
            k_max = min(n, n1)
            ks = np.arange(k + 1, k_max + 1, dtype=int)
            if len(ks) == 0:
                return 0.0
            logps = np.array([logpmf(xx) for xx in ks])
            return float(np.exp(np.logaddexp.reduce(logps)))

        if alternative == 'less':
            pvalue = cdf(c[0, 0])
        elif alternative == 'greater':
            # Same formula as the 'less' case, but with the second column.
            pvalue = sf(c[0, 0] - 1)
        elif alternative == 'two-sided':
            mode = int((n + 1) * (n1 + 1) / (M + 2))
            pexact = pmf(c[0, 0])
            pmode  = pmf(mode)
            epsilon = 1e-14
            gamma = 1 + epsilon

            if abs(pexact - pmode) / max(pexact, pmode) <= epsilon:
                return SignificanceResult(oddsratio, 1.0)

            if c[0, 0] < mode:
                plower = cdf(c[0, 0])
                pvalue = plower + sf(mode)
            else:
                pupper = sf(c[0, 0] - 1)
                pvalue = pupper + cdf(mode)
        else:
            raise ValueError("`alternative` should be one of {'two-sided', 'less', 'greater'}")

        pvalue = min(float(pvalue), 1.0)
        return SignificanceResult(oddsratio, pvalue)

    def normalize(self, np_array_data):
        """如果有效搭配词在过滤后一个都没留下，left_strength 或 right_strength 变成空列表，此函数执行时会报错。
        做了补丁：即使 strength_list 是 []，也不会崩，UI 还能拿到一个合法的 FirthianCollocation 对象（只是里面的 left_strength/right_strength 也是空或全0）"""
        new_data = np.asarray(np_array_data)
        if new_data.size == 0:
            return new_data  # 如果本来就是空，就直接返回空，避免后面崩
        
        # 等价于 transformer.transform(new_data)
        # 直接用 numpy 的 log10 以替换sklearn；保持与原来一致的行为（对非正数产生 -inf/NaN）
        new_data = np.log10(new_data, 
                            where=np.isfinite(new_data), 
                            out=np.full_like(new_data, np.nan, dtype=float))
        # transformer = FunctionTransformer(np.log10)
        # new_data = transformer.transform(new_data)

        # 过滤无效值
        b = np.unique( new_data )
        b = b[b!=0]
        b = b[np.isfinite(b)]
        # 如果过滤后也什么都不剩，就直接返回原始（或者全0，也可以）
        if b.size == 0:
            # 这里我给出一个平滑做法：把所有强度都当成 0.0
            return np.zeros_like(new_data, dtype=float)
        
        min_v = np.min(b)
        max_v = np.max(b)
        # max_v == min_v 也要防一下，否则分母变0
        if max_v == min_v:
            return np.ones_like(new_data, dtype=float)
        new_data = (new_data - min_v) / (max_v-min_v)
        
        return new_data
    

    ###################################################################################
    ## -------------------------- FC Extraction Pipeline ----------------------------##
    ##
    def obtain_fc_pipeline(self, src_path: str, node_word: str, node_pos_list: list=[], reporter: ProgressReporter = None):
        """
        从给定的file_path中提取弗思搭配的管道函数。
        reporter: 可选。用于多层下传进度，用于进度回调/Qt 信号。
        """
        if not reporter:
            reporter = ProgressReporter(lambda *_: None)  # 构造一个安静的默认汇聚器，以兼容用户不传的情况
        
        reporter.report(0, QCoreApplication.translate("CollocationRetriever", "读取语料……"))
        # ============【修改逻辑开始】============
        global _CURRENT_CORPUS_CACHE
        # 检查是否可以直接复用缓存？
        # 如果路径相同，且大小写设置相同，直接复用！
        if (_CURRENT_CORPUS_CACHE["path"] == src_path and 
            _CURRENT_CORPUS_CACHE["case_sensitive"] == self.case_sensitive and
            _CURRENT_CORPUS_CACHE["doc"] is not None):
            self.doc = _CURRENT_CORPUS_CACHE["doc"]
            
        else:
            # 必须重新加载
            self.doc = read_data(src_path, 
                                 self.spacy_api, 
                                 case_sensitive=self.case_sensitive,
                                 reporter=reporter.child(0,18))
            
            # 【关键】更新缓存
            _CURRENT_CORPUS_CACHE["path"] = src_path
            _CURRENT_CORPUS_CACHE["doc"] = self.doc
            _CURRENT_CORPUS_CACHE["case_sensitive"] = self.case_sensitive
        # ============【修改逻辑结束】============
        
        reporter.report(18, QCoreApplication.translate("CollocationRetriever", "收集词频……"))
        self.collect_word_frequency(src_path)

        reporter.report(20, QCoreApplication.translate("CollocationRetriever", "提取搭配……"))
        # 如果不区分大小写，那么节点词也要改成小写
        if not self.case_sensitive:
            node_word = node_word.lower()
        # 节点词的词性：如果参数为空表，则表示全部包含（不作限定）
        valid_node_pos = set()
        for pos, tags in self.tagset.items():
            if pos in node_pos_list:
                valid_node_pos.update(tags)
        leftfd, left_ave_pstns, rightfd, right_ave_pstns = self.obtain_collocation_distribution(node_word, valid_node_pos, reporter=reporter.child(20, 60)) # 下传子区间
        
        N = self.get_typed_word_freq("wordform", "BIG_N")
        if len(valid_node_pos)>0:
            tgt_freq = sum([self.get_node_word_freq(node_word, pos) for pos in valid_node_pos])
        else:
            tgt_freq = self.get_node_word_freq(node_word)
            
        # Get left side collocates
        reporter.report(80, QCoreApplication.translate("CollocationRetriever", "提取搭配……"))
        left_collocates, left_strength, left_pstns, left_pos_list = self.get_collocation_data(leftfd, left_ave_pstns, tgt_freq, N, left=True)
        left_strength = self.normalize(left_strength)
        
        # Get right side collocates
        reporter.report(90, QCoreApplication.translate("CollocationRetriever", "提取搭配……"))
        right_collocates, right_strength, right_pstns, right_pos_list = self.get_collocation_data(rightfd, right_ave_pstns, tgt_freq, N, left=False)
        right_strength = self.normalize(right_strength)
        
        # 返回结果
        return FirthianCollocation(node_word, valid_node_pos, tgt_freq, N, self.metric, 
                                   self.valid_coll_pos, (self.left_window_size, self.right_window_size), self.min_cofreq_percentage, 
                                   self.lang, self.case_sensitive, self.use_lemma, 
                                   left_collocates, left_strength, left_pstns, left_pos_list, 
                                   right_collocates, right_strength, right_pstns, right_pos_list
                                   )


# ==========================================
# Firthian Collocation封装对象
# ==========================================
import json
from nltk.corpus import wordnet as wn

class FirthianCollocation(object):

    def __init__(self, 
                 node_word="", node_pos=[], node_freq=0, total_tok=0, metric="", 
                 coll_pos=[], window_size=(), min_cofreq=0, 
                 lang="", case_sensitive=True, use_lemma=True, 
                 left_collocates=[], left_strength=[], left_pstns=[], left_pos_list=[],
                 right_collocates=[], right_strength=[], right_pstns=[], right_pos_list=[],
                 json_path=""):
        """
        """
        # Meta-info
        self.node_word = node_word
        self.node_pos = list(node_pos) # set集合类型不能被JSON序列化，需转换成列表
        self.node_freq = node_freq
        self.total_tok = total_tok
        self.metric = metric
        self.coll_pos = list(coll_pos)

        self.window_size = window_size
        self.lang = lang
        self.case_sensitive = case_sensitive
        self.use_lemma = use_lemma
        self.min_cofreq = min_cofreq

        # Coll-info
        self.left_collocates = left_collocates
        self.left_strength = left_strength
        self.left_pstns = left_pstns
        self.left_pos_list = left_pos_list
        self.right_collocates = right_collocates
        self.right_strength = right_strength
        self.right_pstns = right_pstns
        self.right_pos_list = right_pos_list

        # Figure parameters
        self.fig_width = 2.5
        self.fig_height = 2

        if json_path:
            self.load_from_json(json_path)
    
    #################################################################################
    ## --------- Dumping and Loading Firtian Collocation in json format -----------##
    ##
    def save_to_json(self, json_file_path: str=""):
        """This function save the obtained Firthian Collocation to a json file. The structure of the json file is as follows:
        {
            LEFT_COLLOCATES_INFO: [ collocate list, stength list, position list, and part-of-speech list ]
            RIGHT_COLLOCATES_INFO: [ collocate list, stength list, position list, and part-of-speech list ]
        }

        Args:
            json_file_path (str): 要导出的json文件路径。如果为空，则会将 JSON 对象dumps并返回
        """
        if not self.node_word:
            print("Warning: Please obtain a Firthian Collocation using obtain_fc_pipeline first!")
            return
        
        save_data = dict()
        save_data.update({"NODE_WORD": self.node_word})
        save_data.update({"NODE_POS": self.node_pos})
        save_data.update({"NODE_FREQ": self.node_freq})
        save_data.update({"TOTAL_TOK": self.total_tok})
        save_data.update({"METRIC": self.metric})
        save_data.update({"COLL_POS": self.coll_pos})

        save_data.update({"WINDOW_SIZE": self.window_size})
        save_data.update({"LANG": self.lang})
        save_data.update({"CASE_SENSITIVE": self.case_sensitive})
        save_data.update({"USE_LEMMA": self.use_lemma})
        save_data.update({"MIN_COFREQ": self.min_cofreq})
            
        left_collocates_info = list(zip(
                self.left_collocates, 
                self.left_strength, 
                self.left_pstns, 
                self.left_pos_list
            ))
        left_collocates_info = sorted(left_collocates_info, key=lambda x:x[1], reverse=True)
        left_collocates_info = [{"collocate":d[0], "strength":d[1], "pstn":d[2], "pos":d[3]}
                                for d in left_collocates_info]
        save_data.update({"LEFT_COLLOCATES": left_collocates_info})
        
        right_collocates_info = list(zip(
                self.right_collocates, 
                self.right_strength, 
                self.right_pstns, 
                self.right_pos_list
            ))
        right_collocates_info = sorted(right_collocates_info, key=lambda x:x[1], reverse=True)
        right_collocates_info = [{"collocate":d[0], "strength":d[1], "pstn":d[2], "pos":d[3]}
                                for d in right_collocates_info]
        save_data.update({"RIGHT_COLLOCATES": right_collocates_info})
        
        if json_file_path:
            with open(json_file_path, "w", encoding="utf-8") as ops:
                json.dump(save_data, ops, ensure_ascii=False, indent=4, separators=(",", ":")) # 数据量大，去掉逗号和冒号后默认带的空格更紧凑
        else:
            return json.dumps(save_data, ensure_ascii=False, indent=4)
    
    def load_from_json(self, json_file_path: str):
        """This function restore a Firthian Collocation from a json file. 

        Args:
            json_file_path (str): 要导入的json文件路径。
        """
        with open(json_file_path, "r", encoding="utf-8") as ips:
            load_data = json.load(ips)

        self.node_word = load_data["NODE_WORD"]
        self.node_pos = load_data.get("NODE_POS", [])
        self.node_freq = load_data.get("NODE_FREQ", 0)
        self.total_tok = load_data.get("TOTAL_TOK", 0)
        self.metric = load_data["METRIC"]
        self.coll_pos = load_data.get("COLL_POS", [])

        self.window_size = load_data["WINDOW_SIZE"]
        self.lang = load_data["LANG"]
        self.case_sensitive = load_data.get("CASE_SENSITIVE", True)
        self.use_lemma = load_data.get("USE_LEMMA", True)
        self.min_cofreq = load_data.get("MIN_COFREQ", 0)

        self.left_collocates, self.left_strength, self.left_pstns, self.left_pos_list = self.decompose_collocate_info(load_data["LEFT_COLLOCATES"])
        self.right_collocates, self.right_strength, self.right_pstns, self.right_pos_list = self.decompose_collocate_info(load_data["RIGHT_COLLOCATES"])
        
        return self
            
    def decompose_collocate_info(self, collocates_info):
        collocates = []
        strength_list = []
        pstns = []
        pos_list = []
        
        for i in range( len(collocates_info) ):
            cur_info = collocates_info[i]
            collocates.append(cur_info['collocate'])
            strength_list.append(cur_info['strength'])
            pstns.append( cur_info['pstn'] )
            pos_list.append( cur_info['pos'] )
        
        return collocates, strength_list, pstns, pos_list
    
    ##################################################################################
    ## ----------------------------- Visualization ---------------------------------##
    ##
    def _filter_collocates(self, collocates, pstns, strength, pstn_filter, y_range):
        """Reduces the scale of a Firthian collocation by:
        (1) the left- & right-side distance to the node;
        (2) the strength of the collocate.

        Args:
            pstns (_type_): _description_
            strength (_type_): _description_
            collocates (_type_): _description_
            colors (_type_): _description_
            pstn_filter (_type_): _description_

        Returns:
            _type_: _description_
        """
        new_collocates = []
        new_pstn = []
        new_strength = []
        
        for i in range(len(collocates)):
            # 距离超出的筛掉
            if abs(pstns[i]) > pstn_filter: continue
            # 强度落在范围之外的筛掉
            elif strength[i] < y_range[0] or strength[i] > y_range[1]: continue
            # 其余保留
            else:
                new_collocates.append( collocates[i] )
                new_pstn.append( pstns[i] )
                new_strength.append( strength[i] )
                
        return new_collocates, new_pstn, new_strength
    
    def _adjust_text_pstn(self, all_texts, fig):
        """This function is obseleme due to the introduction of adjust text.

        Args:
            pstn_list (_type_): _description_
            strength_list (_type_): _description_

        Returns:
            _type_: _description_
        """
        # Modify the expand_text for complex graph. Try to increase the value in x or y will help solve the text overlapping issue.
        vis_texts = [t for t in all_texts if t.get_visible()]
        if vis_texts:
            # 用“可见文本的当前坐标”做一次轻量排版
            xs = [t.get_position()[0] for t in vis_texts]
            ys = [t.get_position()[1] for t in vis_texts]
            adjust_text(
                vis_texts, xs, ys,
                arrowprops=dict(arrowstyle="-", color="blue", lw=0.05), # 当文字被移动太远时，在它和原点之间画一条小箭头（或直线）以保持对应关系。
                # force_explode=(0.04, 0.02), # 设定文字在 x/y 方向上“强制分离”的程度。数值越大，分离越强烈。
                # expand=(1.2, 1.05), # 控制文字之间和文字-点之间的最小距离倍数。
                # explode_radius=120, # 指定一个以原点为中心的爆炸式扩散半径（常用于密集图）。
                #only_move={"text":"xy", "explode":"xy"}, # 限制调整方向，例如只沿 x/y 移动。
                # time_lim=40, # 限制算法运行时间（秒），防止卡死。
                # ensure_inside_axes=False, # 允许文字被移出坐标轴外（默认必须保持在内）。
            )
            fig.canvas.draw_idle()
    
    def _cluster_by_radius(self, xs, ys, labels, strengths, radius, label_n):
            """将两两距离<=radius 的点按连通性聚成簇，返回合并后的 xs, ys, labels, strengths。
            xs: list[float]  (x坐标)
            ys: list[float]  (y/强度坐标，用于散点纵轴)
            labels: list[str]
            strengths: list[float]  (用于颜色映射；这里与 ys 相同，但单独传保持通用性)
            """
            n = len(xs)
            if n == 0:
                return xs, ys, labels, strengths, []

            X = np.column_stack([np.asarray(xs, dtype=float), np.asarray(ys, dtype=float)])
            S = np.asarray(strengths, dtype=float)
            assigned = np.zeros(n, dtype=bool)
            new_xs, new_ys, new_labels, new_strengths, counts = [], [], [], [], []

            diff = X[:, None, :] - X[None, :, :]
            dist = np.sqrt(np.sum(diff * diff, axis=2))

            for i in range(n):
                if assigned[i]:
                    continue
                cluster = {i}
                frontier = {i}
                while frontier:
                    new_frontier = set()
                    for u in frontier:
                        neighbors = np.where((~assigned) & (dist[u] <= radius))[0]
                        for v in neighbors:
                            if v not in cluster:
                                cluster.add(v)
                                new_frontier.add(v)
                    frontier = new_frontier

                idxs = sorted(cluster)
                assigned[idxs] = True

                cx = float(X[idxs, 0].mean())
                cy = float(X[idxs, 1].mean())
                cs = float(S[idxs].mean())

                # 标签按出现顺序去重
                lbls = [labels[k] for k in idxs]
                dedup_lbls = list(dict.fromkeys(lbls))

                # —— 截断显示：超过 label_n 则保留前 label_n 个，并追加 +k —— #
                if label_n is not None and label_n >= 0 and len(dedup_lbls) > label_n:
                    k = len(dedup_lbls) - label_n
                    shown = dedup_lbls[:label_n]# + [f"+{k}"]
                    shown[-1] = shown[-1] + f"+{k}" # 最后一个词后直接拼接 +k，不再加逗号
                else:
                    shown = dedup_lbls
                clabel = ",".join(shown)

                new_xs.append(cx)
                new_ys.append(cy)
                new_labels.append(clabel)
                new_strengths.append(cs)
                counts.append(len(idxs))

            return new_xs, new_ys, new_labels, new_strengths, counts
    
    def visualize_matplotlylib(self, x_range=(5,5), y_range=(-0.05,1.05), 
                               text_font_size: float = 2.5,
                               node_size: float = 6.0,    # 节点词的显示大小
                               node_pos_pct: int = 30,    # 节点词的Y位置（图的百分比）
                               font_family: str = "",     # 用户指定的绘图字体
                               marker_alpha: float = 0.8, # 点透明度
                               marker_size: float = 0.25, # 点基础大小
                               adjust_text_mode: str = "",# 调整标签文本显示的方案
                               scheme_params: Dict[str, Any] = None,  # 优化设置（复杂参数，详见文档）
                               cluster_params: Dict[str, Any] = None, # 聚合设置（复杂参数，详见文档）
                               reporter: ProgressReporter = None
                            ):
        """Visualizing function.

        Args:
            x_range (Union[np.ndarray, List[float]]): x-coordinates of texts 1d array/list.
            y_range (Union[np.ndarray, List[float]]): y-coordinates of texts 1d array/list.
            text_font_size (Union[int, float, optional): size of text. Defaults to 2.5 pt.
            node_pos_pct (Union[int, float, optional: 节点词的Y位置，单位为图的百分比。Defaults to 30 pt.
            font_family
            marker_alpha
            marker_size
            adjust_text_mode (str, optional): 调整标签文本显示的方案，可取 [""|"simple"|"allocate"]。Defaults to "".
            scheme_params (dict, optional): kwargs for some adjust_text_mode:
                - dist_win: (Union[np.ndarray, List[float]]) 供优化方案为allocate时使用。限定标签的远离距离。
            cluster_params (dict, optional): kwargs for clustering scatters:
                - cluster_radio: float = 0.05, 聚合半径（<=0 不聚合） 默认0.05
                - label_n: int = 3, 标签截断阈值（>label_n 就用 +k 省略） 默认3
                - expand_ratio: float = 1.0, 每合并一个点，面积扩大倍率 默认+100%
                如果为None，则表示不进行聚合操作；否则只要给了任意一项内容，会自动按缺省值补全3个参数。

        Returns:
            fig
        """
        if not reporter:
            reporter = ProgressReporter(lambda *_: None)  # 构造一个安静的默认汇聚器，以兼容用户不传的情况
        
        # 安全检查
        if not self.node_word:
            print("Warning: Please obtain a Firthian Collocation using obtain_fc_pipeline first!")
            return
        
        # 字体设置
        if font_family != "":
            # 用户指定了字体（追加几个通用字体作为fallback）
            plt.rcParams["font.family"] = [font_family, "Noto Sans SC"]
        else:
            # 本 app 默认绘图字体为 Noto Sans SC
            plt.rcParams["font.family"] = ["Noto Sans SC"]

        # 复杂参数补全
        if cluster_params is not None:
            default_cluster_params = {"cluster_radio": 0.05, "label_n": 3, "expand_ratio": 1.5}
            for p_key, p_val in default_cluster_params.items():
                if not p_key in cluster_params:
                    cluster_params[p_key] = p_val
        
        # --- Filter out collocates that lie outsides the wanted x/y range.
        reporter.report(10, QCoreApplication.translate("FirthianCollocation", "筛选搭配词……"))
        left_collocates, left_pstns, left_strength = self._filter_collocates(self.left_collocates, self.left_pstns, self.left_strength, x_range[0], y_range)
        right_collocates, right_pstns, right_strength = self._filter_collocates(self.right_collocates, self.right_pstns, self.right_strength, x_range[1], y_range)

        # --- Get scatter data and colors for render
        all_collocates = left_collocates + right_collocates
        all_pstns = left_pstns + right_pstns
        all_strength = left_strength + right_strength

        # --- 可选：密集点聚合成簇
        if cluster_params and cluster_params["cluster_radio"]>0:
            reporter.report(20, QCoreApplication.translate("FirthianCollocation", "点簇聚合……"))
            all_pstns, all_strength, all_collocates, all_strength_for_color, cluster_counts = self._cluster_by_radius(
                all_pstns, all_strength, all_collocates, all_strength, 
                cluster_params["cluster_radio"], cluster_params["label_n"]
            )
            # 散点尺寸也要随簇大小按面积线性放大（封顶 10x）
            scales = [min(10.0, 1.0 + cluster_params["expand_ratio"]*(c-1)) for c in cluster_counts]
        else:
            all_strength_for_color = all_strength
            scales = [1] * len(all_pstns)
        
        # --- 确定每个点的颜色与尺寸
        all_colors = list((40 - np.asarray(all_strength_for_color) * 40).astype(int))
        sizes = [marker_size * sc for sc in scales]
        
        # --- 创建空白画布
        fig, axs = plt.subplots(nrows=1, ncols=1, figsize=(self.fig_width,self.fig_height), dpi=600)
        fig.tight_layout()
        plt.subplots_adjust(left=0.06, right=0.94, bottom=0.06, top=0.94) # 画面边缘腾出一些空白边距
        # 将图顶部和底部的边线调细
        axs.spines["top"].set_linewidth(0.1)
        axs.spines["bottom"].set_linewidth(0.1)
        
        # --- 绘制散点：参数依次为 点的横、纵坐标；点的颜色；点的大小；透明度；开启可点击
        reporter.report(40, QCoreApplication.translate("FirthianCollocation", "绘制散点……"))
        scatters = axs.scatter(all_pstns, all_strength, c=all_colors, s=sizes, alpha=marker_alpha, picker=True)
        scatters.set_pickradius(5)
        
        # --- 网格与刻度线
        axs.set_axisbelow(True)  # 让网格在线下方
        axs.tick_params(right=True, labelright=True,
                        width=0.05, pad=0.01, # 刻度线的粗细；标签-轴线间距
                        grid_alpha=0.4, grid_color="grey", grid_linewidth=0.1, grid_linestyle='--' # 网格线样式
                        )
        axs.grid(True, which='major', axis='both')
        
        # y轴刻度与标签标签
        # axs.set_ylabel("Assoc. Strength", fontsize=2.5, loc='center', labelpad=0.1, fontweight='bold')
        plt.setp(axs.get_yticklabels(), fontsize=text_font_size, fontweight='bold')
        plt.margins(x=0, y=0)
        
        # --- 中心 node_word 和 metric
        node_y = y_range[0] + (y_range[1] - y_range[0]) *node_pos_pct /100.0
        axs.text(0, node_y, 
                 self.node_word, 
                 fontsize=node_size, color="#800080", 
                 ha="center", va="center")
        metric_y = y_range[0] + (y_range[1] - y_range[0]) *(node_pos_pct-6) /100.0 # metric在node下方-6%位置
        axs.text(0, metric_y, 
                 f"[Metric: {self.metric}]", 
                 fontsize=2, color="#800080", 
                 ha="center", va="center")
        
        # --- 坐标轴显示范围
        # x轴左右略留空隙，y轴严格截至上下边界。emit表示不要立即触发重绘（性能优化），auto允许自动调整比例。
        axs.set_xlim(-x_range[0]-0.3, x_range[1]+0.3, emit=False, auto=True)
        axs.set_ylim(y_range[0], y_range[1], emit=False)
        
        # --- x轴刻度与标签
        xticklabels = [f"L{i}" for i in range(x_range[0], 0, -1)] + ["NODE"] + [f"R{i}" for i in range(1, x_range[1]+1) ]
        axs.set_xticks( list(range(-x_range[0], x_range[1]+1)) ) # 设置横轴刻度位置
        axs.set_xticklabels(xticklabels, fontsize=text_font_size, fontweight='bold')

        # --- 如果选择了自动调整文本位置
        reporter.report(60, QCoreApplication.translate("FirthianCollocation", "调整文本位置……"))
        all_texts = []
        if adjust_text_mode == "simple" or adjust_text_mode == "":
            # 预创建标签对象（默认显示，点击切换显/隐）
            for i in range(len(all_collocates)):
                t = axs.text(all_pstns[i], all_strength[i], all_collocates[i], fontsize=text_font_size, clip_on=True)
                all_texts.append(t)
            # 调整坐标位置
            if adjust_text_mode == "simple":
                self._adjust_text_pstn(all_texts, fig)

        elif adjust_text_mode == "allocate":
            # Use textalloc instead of adjust_text
            assert scheme_params and "dist_win" in scheme_params
            axs.set_autoscale_on(False) # 禁止坐标轴自动适应调整，就保持用户输入的要求
            _, _, all_texts, _ = allocate(axs,
                    x = all_pstns,
                    y = all_strength,
                    text_list = all_collocates,
                    textsize = text_font_size,
                    min_distance = scheme_params["dist_win"][0],#0.002,
                    max_distance = scheme_params["dist_win"][1],#0.25,
                    linewidth=0.05,
                    avoid_label_lines_overlap=True,
                    avoid_crossing_label_lines=True,
                    nbr_candidates=1000,
                    linecolor='b',
                    priority_strategy=3,
                    draw_all=True,
                    )
        
        # ====================== 交互逻辑（点击切换标签） ======================
        # 为了能从 scatter 的 pick 结果映射回文本，我们需要知道该点在散点列表中的索引
        # Matplotlib 的 PathCollection 会在 pick_event 中给出 .ind（点索引数组）
        def on_pick(event):
            if event.artist is scatters:
                # toggle text visibility
                for idx in event.ind:
                    txt = all_texts[idx]
                    txt.set_visible(not txt.get_visible())
                # --- 如果选择了自动调整文本位置
                # if auto_adjust_text:
                #     self._adjust_text_pstn(all_texts, fig)
                fig.canvas.draw_idle()

        cid_pick = fig.canvas.mpl_connect('pick_event', on_pick)
        
        return fig
    
    #################################################################################
    ## -------------------- Collocation similarity computation --------------------##
    ##
    def _get_sidely_similarity(self, collocate_data_1, collocate_data_2, window_size, unique_penalty):
        """This function computes the distance between two Firthian collocations.

        Args:
            collocate_data_1 (tuple[] | list[]): (collocates[], strengths[], positions[])
            collocate_data_2 (tuple[] | list[]): (collocates[], strengths[], positions[])
            
        Return:
            a tuple: (相似性结果, 共有词列表, 共有词的相似性列表, FC1的独有词列表, FC2的独有词列表)
        """
        # 找出两个节点的搭配词列表中共有的搭配词
        shared_collocates = list(set(collocate_data_1[0]).intersection( set(collocate_data_2[0]) ))
        unique_collocates_1 = [] # 存放每个搭配的独有词
        unique_collocates_2 = []
        # 构建两个向量，表示它们在共享搭配空间中的表现。
        shared_1 = [0.0 for i in range(len(shared_collocates))]
        shared_2 = [0.0 for i in range(len(shared_collocates))]
        unique_1 = 0 # 独有词（惩罚项）
        unique_2 = 0
        
        for i in range(len(collocate_data_1[0])):
            c = collocate_data_1[0][i]
            s = collocate_data_1[1][i]
            p = collocate_data_1[2][i] / window_size    # Normalize the position -> [0,1]
            if c in shared_collocates:
                idx = shared_collocates.index(c)
                shared_1[idx] = [s, p]
            else:
                unique_collocates_1.append(c)
                unique_1 += 1*s
                
        for i in range(len(collocate_data_2[0])):
            c = collocate_data_2[0][i]
            s = collocate_data_2[1][i]
            p = collocate_data_2[2][i] / window_size    # Normalize the position -> [0,1]
            if c in shared_collocates:
                idx = shared_collocates.index(c)
                shared_2[idx] = [s,p]
            else:
                unique_collocates_2.append(c)
                unique_2 += 1*s
        
        # 若没有共享词，直接返回 0 相似度与空细节
        if len(shared_collocates) == 0:
            return (0.0, [], np.array([], dtype=float), unique_collocates_1, unique_collocates_2)

        # 列表 -> (m,2) 的 numpy 数组
        A = np.asarray(shared_1, dtype=float)
        B = np.asarray(shared_2, dtype=float)
        # 计算共享部分的欧氏距离（只要对角线）：sqrt(sum((A-B)^2, axis=1))
        d = np.sqrt(np.sum((A - B) * (A - B), axis=1))
        # 将距离映射为相似度；两维向量的最大距离是 sqrt( (1-0)^2 + (1-0)^2 ) = sqrt(2)
        shared_sim = (1.0 - d / np.sqrt(2))

        # final = mean(shared_sim) * (1 - λ * (U1 + U2))
        # 共享部分的平均相似度（强度/位置差异越大，越低）
        shared_score = float(np.mean(shared_sim))
        # 用 unique_1/unique_2 做惩罚，但做个简单归一化到 [0,1]
        unique_sum = unique_1 + unique_2
        total = unique_sum + float(np.sum(shared_sim))
        penalty = (unique_sum / total) if total > 0 else 0.0
        # 计算最终结果：如果两个搭配集合共享部分多，且差异小，则 s→1；如果共享词少、独有词多，则 s→0
        final_sim = max(0.0, min(1.0, shared_score * (1.0 - unique_penalty * penalty)))

        # 需要汇报共有词&独有词细节： (相似性结果, 共有词列表, 共有词的相似性, FC1的独有词, FC2的独有词)
        return (final_sim, shared_collocates, shared_sim, unique_collocates_1, unique_collocates_2)
    
    def get_similarity(self, other_fc, unique_penalty=0.8, report_detail=False):
        """Compute Firthian collocation similarity with another saved json files.

        Args:
            other_fc (FirthianCollocation): 要比较的另一个 FirthianCollocation 对象。
            unique_penalty (float): 对独有项的惩罚权重 (一般为0.5~1)。
            report_detail (bool): 是否需要汇报共有词&独有词相关细节。

        Returns:
            a similarity value: 本搭配与传入的搭配之间的距离
        """
        if not self.node_word or not other_fc.node_word:
            print("Warning: The FirthianCollocation data to be compared is not loaded yet!")
            return
        
        # 左、右分别计算相似度
        left_sim, left_shared_collocates, left_shared_sims, left_uniq_1, left_uniq_2 = self._get_sidely_similarity(
            [self.left_collocates, self.left_strength, self.left_pstns], 
            [other_fc.left_collocates, other_fc.left_strength, other_fc.left_pstns], 
            max(self.window_size[0], other_fc.window_size[0]), 
            unique_penalty
        )
        right_sim, right_shared_collocates, right_shared_sims, right_uniq_1, right_uniq_2  = self._get_sidely_similarity(
            [self.right_collocates, self.right_strength, self.right_pstns], 
            [other_fc.right_collocates, other_fc.right_strength, other_fc.right_pstns], 
            max(self.window_size[1], other_fc.window_size[1]), 
            unique_penalty
        )
        # 将左、右两部分取平均
        overall_sim = (left_sim + right_sim)/2
        
        # 准备结果
        result = {
            "OVERALL_SIMILARITY": overall_sim
        }

        if report_detail is True:
            # 需要给出 相似性结果, 共有词列表, 共有词的相似性列表, FC1的独有词列表, FC2的独有词列表
            left_info = {
                "SIMILARITY": left_sim,
                "SHARED": {w: float(s) for w, s in sorted(zip(left_shared_collocates, left_shared_sims), key=lambda x: x[1], reverse=True)}, # 配对并按相似度排序
                "UNIQUE_1": left_uniq_1,
                "UNIQUE_2": left_uniq_2
            }
            result.update({"LEFT": left_info})
            right_info = {
                "SIMILARITY": right_sim, 
                "SHARED": {w: float(s) for w, s in sorted(zip(right_shared_collocates, right_shared_sims), key=lambda x: x[1], reverse=True)}, # 配对并按相似度排序
                "UNIQUE_1": right_uniq_1,
                "UNIQUE_2": right_uniq_2
            }
            result.update({"RIGHT": right_info})
        
        return json.dumps(result, ensure_ascii=False, indent=4)
    
    ##################################################################################
    ## -------------------- Semantic Abstraction using wordnet ---------------------##
    ##
    def lowest_common_hypernym_iteration(self, lch_info, wn, new_lch_info):
        
        if self.lowest_common_hypernym_iteration_count > 1: return
                
        lch_info_list = list(lch_info.items())
        num_lch = len(lch_info_list)
        
        for i in range(num_lch-1):
            for j in range(i+1, num_lch):

                # get accumulated scores
                s_1 = lch_info_list[i][0]
                s_2 = lch_info_list[j][0]

                # get accumulated objects
                data_1 = lch_info_list[i][1] 
                data_2 = lch_info_list[j][1]

                cur_lches = s_1.lowest_common_hypernyms(s_2)
                added = False
                for lch in cur_lches:
                    if lch != s_1 and lch != s_2:
                        # 【修改点1】：如果 lch 不在新字典里，先初始化结构
                        if lch not in new_lch_info:
                            new_lch_info[lch] = {"score": 0.0, "sources": set()}
                        # 【修改点2】：分数累加，来源集合合并 (Union)
                        new_lch_info[lch]["score"] += data_1["score"] + data_2["score"]
                        new_lch_info[lch]["sources"].update(data_1["sources"])
                        new_lch_info[lch]["sources"].update(data_2["sources"])
                        added = True
                if added:
                    if s_1 in lch_info: lch_info.pop(s_1)
                    if s_2 in lch_info: lch_info.pop(s_2)
        
        self.lowest_common_hypernym_iteration_count += 1

        # 检查是否为空
        if not new_lch_info:
            return
        else:
            lch_info.update(new_lch_info)
            self.lowest_common_hypernym_iteration(lch_info, wn, {})
    
    def non_linear_activation(self, collocate_strength_dict):
        """
        数学辅助函数，用于处理分数值。使用一个类 Sigmoid 函数 v/(1+v) 将累加后可能很大的强度值压缩到一个标准化的区间 [0,1)，表示该语义概念的“置信度”或“激活程度”。
        
        :param collocate_strength_dict: Description
        """
        for c, data in collocate_strength_dict.items():
            v = data["score"]
            if v <= 0 or v != v:    # v!=v 是为了防 NaN
                collocate_strength_dict[c]["score"] = 0.0
            else:
                collocate_strength_dict[c]["score"] = v / (1.0 + v)
    
    def semantic_abstraction(self, side="left", 
                             wanted_pos={"VERB", "ADJ", "NOUN"}, 
                             output_dir="", 
                             reporter: ProgressReporter = None):
        """This function reads in a Firthian collocation in json format and retrieves concepts from lexical ontology. For the moment, wordnet is supported. 
        Resulted strength should be used with awareness of pos distinction.
        """
        if not reporter:
            reporter = ProgressReporter(lambda *_: None)  # 构造一个安静的默认汇聚器，以兼容用户不传的情况
            
        lang_mapping = {
            "en": "eng",
            "zh": "cmn",
            "ja": "jpn",
            "fr": "fra",
            # "de": "deu"
        }
        if self.lang not in lang_mapping.keys():
            raise NotImplementedError(
                f"Language '{self.lang}' is not supported for semantic abstraction. "
                f"Supported: {list(lang_mapping.keys())}"
            )
        
        pos_mapping = {"VERB": "v", "ADJ":"a", "NOUN":"n"}
        
        # === 修改开始：数据准备阶段 ===
        collocates = []
        strength = []
        pos = []

        if side=="left":
            collocates = self.left_collocates
            strength = self.left_strength
            pos = self.left_pos_list
        elif side=="right":
            collocates = self.right_collocates
            strength = self.right_strength
            pos = self.right_pos_list
        elif side == "both":
            # 【核心逻辑】将左侧和右侧搭配词合并为一个列表
            # 使用字典进行去重和合并：Key=(word, pos), Value=list_of_strengths
            merge_map = {}
            
            # 定义辅助闭包：将单侧数据填入字典
            def _fill_map(cols, strs, ps):
                for c, s, p in zip(cols, strs, ps):
                    # 只有词形和词性都相同才视为同一个搭配（例如 left的 light/NOUN 和 right的 light/ADJ 不合并）
                    key = (c, p) 
                    if key not in merge_map:
                        merge_map[key] = []
                    merge_map[key].append(s)

            # 分别填入左侧和右侧数据
            _fill_map(self.left_collocates, self.left_strength, self.left_pos_list)
            _fill_map(self.right_collocates, self.right_strength, self.right_pos_list)

            # 重构为列表
            for (c, p), s_list in merge_map.items():
                collocates.append(c)
                pos.append(p)
                # 【策略】计算平均强度 (sum / len)
                # 如果只出现在一侧，len为1，平均值即原值；如果两侧都有，则取平均
                avg_s = sum(s_list) / len(s_list)
                strength.append(avg_s)

        # 【修改点4】：不再使用 defaultdict(float)
        # 结构示例： { synset_obj: {"score": 1.5, "sources": {"apple", "pear"}} }
        synset_info = {} # Used to store synsets without hierarchy
        lch_info = {} # Used to store lowest common hypernyms
        
        self.lowest_common_hypernym_iteration_count = 0
        num_collocates = len(collocates)
        
        # Choose the most frequent lowerest common synset                
        for i in reporter.wrap(range(num_collocates-1),
                                start=0, end=100, message_each=QCoreApplication.translate("CollocationRetriever", "归并搭配词……")):
            pos1 = pos[i]
            if pos1 not in wanted_pos: continue
            collocate1 = collocates[i]                  
            strength1 = strength[i]
            synsets1 = wn.synsets(
                collocate1, 
                pos=pos_mapping[pos1],
                lang=lang_mapping[self.lang]
            )
            if not synsets1: continue
            
            # Adjectives have no synset hierarchy, therefore they rely only on synset identity.
                                
            has_lch = False      
            for j in range(i+1, num_collocates):
                pos2 = pos[j]
                if pos2 not in wanted_pos: continue
                collocate2 = collocates[j]
                strength2 = strength[j]
                if collocate1 == collocate2 or pos1 != pos2: 
                    continue

                synsets2 = wn.synsets(
                    collocate2, 
                    pos=pos_mapping[pos2],
                    lang=lang_mapping[self.lang]
                ) 
                if not synsets2: continue

                # Obtain lowest common hypernyms
                for s1 in synsets1:
                    for s2 in synsets2:
                        lches = s1.lowest_common_hypernyms(s2)
                        if lches: has_lch = True              
                        for lch in lches:
                            # 【修改点5】：初始化并记录来源
                            if lch not in lch_info:
                                lch_info[lch] = {"score": 0.0, "sources": set()}
                            lch_info[lch]["score"] += (strength1 + strength2)
                            # 使用 set 来自动去重
                            lch_info[lch]["sources"].add(collocate1)
                            lch_info[lch]["sources"].add(collocate2)
        
            if has_lch == False:
                for s in synsets1:
                    # 【修改点6】：无层级概念也要记录来源
                    if s not in synset_info:
                        synset_info[s] = {"score": 0.0, "sources": set()}
                    synset_info[s]["score"] += strength1
                    synset_info[s]["sources"].add(collocate1)
                    
        self.lowest_common_hypernym_iteration_count += 1
                                    
        #self.lowest_common_hypernym_iteration(lch_info, wn, defaultdict(float))
        
        # Reduce to range [0,1]
        self.non_linear_activation(synset_info)
        self.non_linear_activation(lch_info)

        # Save synsets in two categories: synsets without hierarchy (adjectives) and synsets with hierarchy
        # 按值排序
        # 【修改点7】：输出格式调整，将 set 转为 list 以便 JSON 序列化
        # 数据解包：data 包含 score 和 sources
        synsets_without_hierarchy = sorted(
            [
                {
                    "synset": s.name(), 
                    "score": data["score"], 
                    "source_words": ", ".join(list(data["sources"])) # 转 list 最后合并成字符串
                } 
                for s, data in synset_info.items()
            ],
            key=lambda x: x["score"], 
            reverse=True
        )
        
        synsets_with_hierarchy = sorted(
            [
                {
                    "synset": s.name(), 
                    "score": data["score"], 
                    "source_words": ", ".join(list(data["sources"])) # 转 list 最后合并成字符串
                } 
                for s, data in lch_info.items()
            ],
            key=lambda x: x["score"], 
            reverse=True
        )
        
        # 打包成字典
        result = {
            "HYPERNYMS": synsets_with_hierarchy,
            "DIRECTS": synsets_without_hierarchy
        }
        if output_dir:
            output_path = os.path.join(output_dir, f"{self.node_word}_{self.metric}_synsets.json")
            with open(output_path, "w", encoding="utf-8") as ops:
                json.dump(result, ops, ensure_ascii=False, indent=4, separators=(",", ":"))

        return json.dumps(result, ensure_ascii=False, indent=4)

    # def visualize_abstraction(self, abstraction_result: dict, top_n=20):
    #     """
    #     将语义抽象结果绘制为横向条形图。
    #     abstraction_result: semantic_abstraction 返回的字典对象
    #     """
    #     # 1. 数据准备
    #     # 合并 HYPERNYMS 和 DIRECTS，或者只看 HYPERNYMS (通常更有意义)
    #     # 这里我们将两者合并排序，展示最强的概念
    #     data = abstraction_result.get("HYPERNYMS", []) + abstraction_result.get("DIRECTS", [])
        
    #     # 按分数降序排序，取前 Top N
    #     data = sorted(data, key=lambda x: x["score"], reverse=True)[:top_n]
        
    #     if not data:
    #         return None

    #     # 提取绘图数据
    #     synsets = [item["synset"] for item in data]
    #     scores = [item["score"] for item in data]
    #     # 为了让 barh 从上到下显示最大的，需要反转列表
    #     synsets = synsets[::-1]
    #     scores = scores[::-1]

    #     # 2. 绘图
    #     fig, ax = plt.subplots(figsize=(8, 6), dpi=100) # 尺寸可根据 UI 调整
        
    #     # 绘制横向条形图
    #     bars = ax.barh(synsets, scores, color="#66b3ff", edgecolor="none", height=0.6)
        
    #     # 3. 美化
    #     ax.spines['top'].set_visible(False)
    #     ax.spines['right'].set_visible(False)
    #     ax.spines['left'].set_visible(False)
    #     ax.spines['bottom'].set_visible(False)
        
    #     # 隐藏 X 轴刻度 (因为我们会直接标数值)
    #     ax.xaxis.set_visible(False)
        
    #     # 设置 Y 轴标签字体
    #     plt.setp(ax.get_yticklabels(), fontsize=10, fontweight="bold", color="#333333")
        
    #     # 在条形图右侧/内部标注数值
    #     for bar, score in zip(bars, scores):
    #         width = bar.get_width()
    #         # 标注 Score
    #         ax.text(width + 0.01, # x 坐标
    #                 bar.get_y() + bar.get_height()/2, # y 坐标
    #                 f"{score:.4f}", 
    #                 ha='left', va='center', fontsize=9, color="#555555")

    #     ax.set_title(f"Top {top_n} Semantic Concepts for '{self.node_word}'", fontsize=12, pad=10)
    #     fig.tight_layout()
        
    #     return fig
    
    def visualize_abstraction(self, abstraction_result: dict, top_n=15, top_k_source=3):
        """
        使用棒棒糖图 (Lollipop Chart) 优化语义抽象可视化。
        包含具体义项 ID (如 change.v.02) 和来源词展示。

        参数:
        - top_n: 展示前多少个语义类
        - top_k_source: 在圆点旁展示前多少个来源词
        """
        # 1. 数据准备
        data = abstraction_result.get("HYPERNYMS", []) + abstraction_result.get("DIRECTS", [])
        
        # 按分数降序排序，取前 Top N
        data = sorted(data, key=lambda x: x["score"], reverse=True)[:top_n]
        
        if not data:
            return None

        # 反转列表，以便在图表中排名第一的显示在最上方
        data = data[::-1]
        
        # 提取数据
        raw_labels = [item["synset"] for item in data]
        scores = [item["score"] for item in data]

        # --- 新增功能: 提取来源词 ---
        source_texts = []
        for item in data:
            # 获取来源词列表，默认为空列表
            # 假设 json 中的 key 是 "source_words"，且是一个字符串列表
            sources = [s.strip() for s in item.get("source_words", "").split(',') if s.strip()]
            
            # 截取前 k 个
            top_sources = sources[:top_k_source]
            
            # 格式化文本，例如: "modify, alter"
            if top_sources:
                text = ", ".join(top_sources)
                # 如果来源词还有更多，可以加个省略号 (可选)
                if len(sources) > top_k_source:
                    text += "..."
                source_texts.append(f"[{text}]")
            else:
                source_texts.append("")

        # 2. 绘图设置
        fig, ax = plt.subplots(figsize=(9, 6), dpi=150) # 提高 DPI 让文字更清晰
        
        # --- 优化 B: 动态 X 轴范围 ---
        # 计算数据的范围，稍微留一点 buffer，让差异显现出来
        min_score = min(scores)
        max_score = max(scores)
        padding = (max_score - min_score) * 0.25 if max_score != min_score else 0.001
        xlim_min = min_score - padding
        xlim_max = max_score + (padding * 0.8) # 右侧留出一点空间给分数
        
        ax.set_xlim(xlim_min, xlim_max)

        # 3. 绘制棒棒糖图
        # (1) 画线 (Stem)
        ax.hlines(y=range(len(raw_labels)), xmin=xlim_min, xmax=scores, color='#cccccc', alpha=0.5, linewidth=1.5)
        
        # (2) 画点 (Head)
        # s 参数控制点的大小，zorder 确保点在线上方
        scatter = ax.scatter(scores, range(len(raw_labels)), s=120, zorder=3)

        # 4. 美化布局
        # 设置 Y 轴标签
        ax.set_yticks(range(len(raw_labels)))
        ax.set_yticklabels(raw_labels, fontsize=9, fontfamily='Segoe UI', fontweight='medium', color="#444444")
        
        # 隐藏边框
        ax.spines['top'].set_visible(False)
        ax.spines['right'].set_visible(False)
        ax.spines['left'].set_visible(False)
        ax.spines['bottom'].set_visible(True)
        ax.spines['bottom'].set_color('#eeeeee') # 底部边框淡化
        
        # X 轴刻度美化
        ax.tick_params(axis='x', colors="#000000", labelsize=9)
        
        # --- 优化 D: 数值标注 ---
        for i, (score, src_text) in enumerate(zip(scores, source_texts)):
            # A. 标注分数 (加粗，颜色跟随点)
            ax.text(score + (padding * 0.12), i, 
                    f"{score:.4f}", 
                    va='center', fontsize=9, fontweight='bold')
            
            # B. 来源词：放在圆点的【下方】且【向左对齐】(依附于横线)
            # y = i - 0.25 让文字下沉
            # ha='right' 让文字的尾部对齐分数值，形成“注解”的感觉
            if src_text:
                ax.text(score, i - 0.25, 
                        src_text, 
                        va='center', ha='right',  # 关键：右对齐，使其位于线条下方
                        fontsize=7, color="#5E5E5E")

        # 标题
        ax.set_title(f"Top Concepts for '{self.node_word}'", 
                    loc='left', fontsize=12, fontweight='bold', color="#333333", pad=12)
        # plt.tight_layout()
        plt.subplots_adjust(left=0.2, right=0.95, top=0.9, bottom=0.1)
        return fig
    

# ==========================================
# 轻量级 KWIC 检索器
# ==========================================
class ConcordanceSearcher:

    def __init__(self, 
                 lang: str = "en", 
                 case_sensitive: bool = True, 
                 use_lemma: bool = False):
        self.lang = lang
        self.case_sensitive = case_sensitive
        self.use_lemma = use_lemma
        # 按需初始化 spacy，仅当缓存未命中需要重新加载文件时才用到
        self.spacy_api = SpacyAPI(lang) 

    def _get_lemma(self, token):
        # 返回给定 token 的词形
        if self.lang in ["en", "fr", "de", "ja"]:
            return token.lemma_
        elif self.lang == "zh":
            # Chinese spacy_tok does not has .lemma_ item, use .text instead.
            return token.text
        
    def search(self, 
               src_path: str, 
               node_word: str, 
               collocate_word: str, 
               window_size: tuple, 
               side: str = "Both", 
               coll_pos: str = "",
               reporter: ProgressReporter = None):
        """
        执行 KWIC 检索。
        优先使用全局缓存中的 Doc 对象，实现零延迟响应。
        """
        if not reporter:
            reporter = ProgressReporter(lambda *_: None)

        global _CURRENT_CORPUS_CACHE

        # 1. 获取语料对象 (Doc)
        doc = None
        # 检查缓存是否可用 (路径匹配 & 对象存在 & 大小写模式一致)
        # 注意：如果用户改了大小写设置，必须重读，因为 token.text/lemma 的存储方式可能受影响
        if (_CURRENT_CORPUS_CACHE["path"] == src_path and 
            _CURRENT_CORPUS_CACHE["doc"] is not None and 
            _CURRENT_CORPUS_CACHE["case_sensitive"] == self.case_sensitive):
            
            # reporter.report(10, "Hit Cache!") # 调试用
            doc = _CURRENT_CORPUS_CACHE["doc"]
        else:
            # 缓存未命中（极少情况），降级为从磁盘读取
            # reporter.report(10, "加载语料中……")
            try:
                doc = read_data(src_path, self.spacy_api, self.case_sensitive)
                # 顺便更新缓存，造福后续操作
                _CURRENT_CORPUS_CACHE["path"] = src_path
                _CURRENT_CORPUS_CACHE["doc"] = doc
                _CURRENT_CORPUS_CACHE["case_sensitive"] = self.case_sensitive
            except Exception as e:
                return [] # 或者抛出异常

        if not doc:
            return []

        # 2. 准备搜索参数
        kwic_results = []
        l_win, r_win = window_size
        
        # 目标词预处理 (Case Sensitivity)
        target_node = node_word
        target_coll = collocate_word
        if not self.case_sensitive:
            target_node = target_node.lower()
            target_coll = target_coll.lower()

        # reporter.report(30, "扫描句子……")

        # 3. 扫描句子
        for sent in doc.sents:
            tokens = list(sent)

            # Step A. 找节点词
            node_indices = []
            for t in tokens:
                # 和 CollocationRetriever 保持一致：节点词始终取 lemma，无须判断 self.use_lemma
                check_t = self._get_lemma(t) # 
                if not self.case_sensitive: check_t = check_t.lower()
                
                if check_t == target_node:
                    node_indices.append(t.i)
            
            if not node_indices: continue

            # Step B. 找搭配词
            for node_idx in node_indices:
                # 根据 side 限制搜索窗口
                # side 参数来自表格点击，通常是 "Left" 或 "Right"
                start_idx = node_idx # 默认不包含左
                end_idx = node_idx   # 默认不包含右
                
                if side == "Left":
                    # 只看左边窗口: [max(sent.start, node-l_win), node)
                    start_idx = max(sent.start, node_idx - l_win)
                    end_idx = node_idx
                elif side == "Right":
                    # 只看右边窗口: (node, min(sent.end, node+r_win+1)]
                    start_idx = node_idx + 1
                    end_idx = min(sent.end, node_idx + r_win + 1)
                else:
                    # Both (兼容逻辑)
                    start_idx = max(sent.start, node_idx - l_win)
                    end_idx = min(sent.end, node_idx + r_win + 1)

                if start_idx >= end_idx: continue # 窗口无效
                
                window_tokens = doc[start_idx : end_idx]
                found = False
                found_token_idx = -1  # <--- 用于记录究竟是哪个词匹配上了

                for t in window_tokens:
                    if t.i == node_idx: continue # 跳过自己(双保险)

                    # 1. 词性检查 (POS Check)
                    # coll_pos 可能是 "VERB", "NOUN" 等，Spacy 的 tag 是 .pos_
                    if coll_pos and t.pos_ != coll_pos:
                        continue
                    
                    # 2. 原形检查（Lemma Check）
                    check_c = self._get_lemma(t) if self.use_lemma else t.text
                    if not self.case_sensitive: check_c = check_c.lower()

                    if check_c == target_coll:
                        found = True
                        found_token_idx = t.i # <--- 锁定目标词的位置
                        break # 确认该节点词周围有搭配词即可，无需重复
                
                if found:
                    # C. 提取 KWIC 片段 (扩展上下文)
                    # 前后各取 15 个词作为上下文展示
                    display_l = max(sent.start, node_idx - 15)
                    display_r = min(sent.end, node_idx + 15)
                    
                    # --- 【修改核心】手动组装带高亮的字符串 ---
                    def _build_rich_text(start, end, highlight_idx):
                        chunks = []
                        for i in range(start, end):
                            t = doc[i]
                            txt = t.text
                            # 如果当前词是找到的搭配词，加粗标红
                            if i == highlight_idx:
                                # 使用 HTML 格式
                                txt = f"<b><font color='red'>{txt}</font></b>"
                            chunks.append(txt + t.whitespace_)
                        return "".join(chunks).strip()
                    
                    # 分别构建左、中、右
                    pre_text = _build_rich_text(display_l, node_idx, found_token_idx)
                    key_text = tokens[node_idx - sent.start].text_with_ws
                    post_text = _build_rich_text(node_idx + 1, display_r, found_token_idx)
                    
                    kwic_results.append({
                        "pre": pre_text,
                        "key": key_text,
                        "post": post_text
                    })
                    
                    # 限制返回数量，防止 UI 卡死
                    if len(kwic_results) >= 500:
                        break
            
            if len(kwic_results) >= 500:
                break
        
        # reporter.report(100, "检索完成")
        return kwic_results
    

if __name__ == "__main__":
    # 要处理的三个 txt 文件
    txt_files = [
        r"./dist/workshop_data/CLEC_preprocessed/O_ST2_UTF.txt",
        # r"./data/text2.txt",
        # r"./data/text3.txt",
    ]

    # 38 个目标动词（注意：要和 spaCy 的 lemma 一致）
    target_verbs = [
        "become", 
    ]

    # 输出目录（自动创建）
    out_dir = "./fc_outputs"
    os.makedirs(out_dir, exist_ok=True)

    metric = "ΔP"

    for src_path in txt_files:
        print(f"\n=== 处理语料: {src_path} ===")

        # 每个文件单独建一个 retriever，避免 self.doc 沿用上一个文件
        retriever = CollocationRetriever(
            lang="en",
            metric=metric,
            winsize=(5, 5),
            case_sensitive=True,          # 通常英文搭配不区分大小写更稳
            min_cofreq_percentage=0.0025,  # 低频搭配过滤阈值，按需要改
            coll_pos_filter=[]             # 搭配词词性不过滤（保留所有）
        )

        for verb in target_verbs:
            print(f"  -> 抽取动词 {verb} 的弗思搭配……", end="", flush=True)

            # 节点词词性：只要动词，因此 node_pos_list=["verb"]
            fc = retriever.obtain_fc_pipeline(
                src_path=src_path,
                node_word=verb,
                node_pos_list=["verb"]
            )

            # 构造输出文件名：<语料名>_<动词>.<metric>.json
            base_name = os.path.splitext(os.path.basename(src_path))[0]
            out_json = os.path.join(out_dir, f"{base_name}_{verb}.{metric}.json")

            fc.save_to_json(out_json)
            print(f" 已保存到 {out_json}")