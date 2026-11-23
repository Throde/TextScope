# fonts.py
from matplotlib import font_manager as fm


# 常见中文字体（跨平台候选）
CJK_FAMILIES = [
    "Noto Sans SC", "Noto Serif SC", "Noto Sans CJK SC", "Noto Serif CJK SC", # Google
    "Source Han Sans SC", "Source Han Serif SC",    # Adobe 思源
    "Microsoft YaHei", "SimHei", "SimSun", "KaiTi", # Windows 常见
    "PingFang SC", "Hiragino Sans GB",              # macOS 常见
]

# 常见英文字体
LATIN_FAMILIES = [
    "DejaVu Sans", "DejaVu Serif", "Arial", "Helvetica",
    "Times New Roman", "Liberation Sans", "Liberation Serif",
    "Calibri", "Cambria"
]

def detect_available_families(pref_list):
    """返回 [(family_name, font_path)]，只保留本机已安装的条目；去重并保持偏好顺序。"""
    # 建立 family -> path 的映射（多个文件取第一个即可）
    fam2path = {}
    for f in fm.fontManager.ttflist:
        fam2path.setdefault(f.name, f.fname)

    result = []
    seen = set()
    for fam in pref_list:
        if fam in fam2path and fam not in seen:
            result.append((fam, fam2path[fam]))
            seen.add(fam)
    return result

# 用 matplotlib.font_manager 枚举系统字体，和一份“常见字体白名单”做交集，获取可用的中/英字体
# [(family_name, font_path)]
CJK_LIST = detect_available_families(CJK_FAMILIES)
LATIN_LIST = detect_available_families(LATIN_FAMILIES)