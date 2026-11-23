#!/usr/bin/env python
# -*- coding: utf-8 -*-

""" Corpus Reader module.

(1) Read in the raw texts in the same directory, or one file, or just a list of paragraphs.
(2) use spaCy to parse the raw text and return spaCy Doc. 
"""

import logging, os
import chardet, re
from spacy.tokens import Doc


from .spacy_api import SpacyAPI
from .progress_reporter import ProgressReporter


from textacy import preprocessing
preproc = preprocessing.make_pipeline(
                preprocessing.replace.hashtags, # "今天#好天气" → "今天 好天气" 把 #话题词 统一替换成一般文本形式
                preprocessing.replace.urls, # "访问 http://example.com" → "访问 <URL>" 把 URL 替换为占位符 <URL>
                preprocessing.normalize.hyphenated_words, # 处理连字符词，比如把断行用连字符连接的词合并。"state-\nof-the-art" → "state of the art" 或 "state-of-the-art"（取决于 textacy 规则）
                preprocessing.normalize.quotation_marks, # “ ” 「 」 《 》 ‘ ’ → " 统一文本中的各种引号形式。
                preprocessing.normalize.whitespace, # 清理空白符，连续空格压缩成一个
                preprocessing.normalize.bullet_points # 标准化项目符号（bullet points），去掉 "•" "◦" "-" "*" "●" 等符号或转换为统一格式
            )



def read_file(src_file: str, 
              spacy_api: SpacyAPI, 
              case_sensitive: bool = True, 
              merge_noun_chunks: bool = False, 
              merge_entities: bool = False,
              reporter: ProgressReporter = None
              ):
    """Read a single input file and use spacy to pre-process.

    Args:
        src_file (path): 文件路径。
        spacy_api (SpacyAPI): spacy管道对象。
        reporter (ProgressReporter): 可多层下传进度，用于进度回调/Qt 信号。

    Returns:
        spacy.tokens.Doc or None: 合并后的总 Doc；若路径为空则返回 None。
    """
    # 仅可读取txt文件
    if not src_file.lower().endswith(".txt"):
        print(f"Skip reading non-txt file: {src_file}")
        return None
    
    doc = None
    try:
        # detect encoding format
        with open(src_file, "rb") as ips:
            sample = ips.read(65536)  # 读取前64KB字节来检测
            ecd = chardet.detect(sample)["encoding"] or "utf-8" # 兜底为utf-8
        
        with open(src_file, "r", encoding=ecd, errors="ignore") as ips:
            text = ips.read()
        
        text = preproc(text)
        text = re.sub("\n", " ", text)

        if not case_sensitive:
            text = text.lower()  # ✅ 关闭大小写：一步到位

        doc = spacy_api.pipeline(text, 
                                 merge_noun_chunks=merge_noun_chunks, 
                                 merge_entities=merge_entities,
                                 reporter=reporter)
        # doc_bin = DocBin(docs=docs)
        # doc_bin.to_disk(docbin_file_path)
    except Exception as e:
        logging.error(f"Error in reading/parsing file: {src_file}")
        logging.exception(e)

    return doc


def read_directory(src_dir, 
                   spacy_api: SpacyAPI, 
                   case_sensitive: bool = True, 
                   merge_noun_chunks: bool = False, 
                   merge_entities: bool = False, 
                   reporter: ProgressReporter = None
                   ):
    """读取目录下所有txt文本文件，合并成大Doc。

    Args:
        src_dir (path): 文件夹路径。
        spacy_api (SpacyAPI): spacy管道对象。
        reporter (ProgressReporter): 可多层下传进度，用于进度回调/Qt 信号。

    Returns:
        spacy.tokens.Doc or None: 合并后的总 Doc；若目录为空则返回 None。
    """
    docs = []

    for root, _, fns in os.walk(src_dir):
        for fn in fns:
            # 仅可读取txt文件
            if not fn.lower().endswith(".txt"):
                continue
            
            path_fn = os.path.join(root, fn)
            doc = read_file(path_fn, 
                            spacy_api, 
                            case_sensitive=case_sensitive, 
                            merge_noun_chunks=merge_noun_chunks, 
                            merge_entities=merge_entities, 
                            reporter=reporter)
            if doc is not None:
                docs.append(doc)
    
    return Doc.from_docs(docs) # 合并多个 Doc 为一个 Doc



# =============================================
# 对外的统一、智能调用接口
# =============================================
def read_data(input_path: str, 
              spacy_api: SpacyAPI, 
              case_sensitive: bool = True, 
              merge_noun_chunks: bool = False, 
              merge_entities: bool = False, 
              reporter: ProgressReporter = None
              ) -> Doc | None:
    """
    智能读取语料文件或目录，返回一个处理后的 spaCy Doc。

    Args:
        input_path (str): 文件路径、目录路径，或多个文件（以分号 ; 分隔）
        spacy_api (SpacyAPI): spacy管道对象。
        merge_noun_chunks (bool, optional): 是否合并名词短语。默认 False。
        merge_entities (bool, optional): 是否合并命名实体。默认 False。
        reporter (ProgressReporter): 可多层下传进度，用于进度回调/Qt 信号。

    Returns:
        spacy.tokens.Doc or None: 合并后的 Doc 对象（若出错或无内容则返回 None）
    """
    if not input_path:
        logging.warning("read_data: 空输入路径。")
        return None
    
    if not reporter:
        reporter = ProgressReporter(lambda *_: None)  # 构造一个安静的默认汇聚器，以兼容用户不传的情况

    if os.path.isfile(input_path):
        return read_file(
            input_path,
            spacy_api,
            case_sensitive=case_sensitive,
            merge_noun_chunks=merge_noun_chunks,
            merge_entities=merge_entities,
            reporter=reporter
        )
    elif os.path.isdir(input_path):
        return read_directory(
            input_path,
            spacy_api,
            case_sensitive=case_sensitive,
            merge_noun_chunks=merge_noun_chunks,
            merge_entities=merge_entities,
            reporter=reporter
        )
    else:
        logging.error(f"路径不存在或不可访问：{input_path}")
        return None