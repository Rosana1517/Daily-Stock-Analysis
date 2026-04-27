from __future__ import annotations

import re


TITLE_TRANSLATIONS = {
    "US justice department drops probe into Fed chairman Jerome Powell": "美國司法部停止調查聯準會主席鮑威爾",
    "White House memo claims mass AI theft by Chinese firms": "白宮備忘錄稱中國企業大規模竊取人工智慧技術",
    "Which airlines are cancelling flights to the UK - and what can you do?": "多家航空公司取消飛往英國航班，旅客需留意改票與退票",
    "Meta to cut one in 10 jobs after spending billions on AI": "Meta 在大量投入人工智慧後計畫裁減約一成職缺",
    "Warner Bros shareholders approve Paramount's $111bn takeover": "華納兄弟股東通過派拉蒙 1110 億美元收購案",
    "Asos demands £7m from US as firms rush to claim tariff refunds": "企業申請關稅退費，Asos 向美方要求 700 萬英鎊",
    "AI is already leading to fewer jobs for young people, says Sunak": "蘇納克表示 AI 已導致年輕人工作機會減少",
    "Anthropic investigating claim of unauthorised access to Mythos AI tool": "Anthropic 調查 Mythos 人工智慧工具疑似遭未授權存取",
    "Meta to track workers' clicks and keystrokes to train AI": "Meta 將追蹤員工點擊與鍵盤操作，用於訓練人工智慧",
    "Police identify the body of 1 missing USF student, second still missing as roommate is charged": "警方確認一名失蹤學生遺體，另一人仍失蹤且室友遭起訴",
    "US imposes sanctions on a China-based oil refinery and 40 shippers over Iranian oil": "美國因伊朗石油問題制裁中國煉油廠與 40 家航運商",
    "Thousands of EV Car Leases Are Ending Soon, Giving Buyers a More Affordable Option": "大量電動車租約即將到期，買方可能有更便宜選擇",
    "Appeals court says Trump’s asylum ban at the border is illegal, agreeing with lower court": "上訴法院維持下級法院看法，認定川普邊境庇護禁令違法",
    "Correspondents’ Dinner’s biggest moments involve laughs, cringing and high-stakes politics": "白宮記者晚宴焦點包含笑料、尷尬場面與高風險政治",
    "FDA plans ultra-fast review of three psychedelic drugs following Trump directive": "川普指示後，美國食品藥物管理局計畫快速審查三種迷幻藥物",
    "In Baltic skies, NATO and Russian pilots size each other up warily but without a tilt into war": "波羅的海上空北約與俄羅斯飛行員互相試探但未升高為衝突",
    "Soldier Used Classified Information to Bet on Maduro’s Ouster, U.S. Says": "美方稱士兵利用機密資訊押注馬杜羅下台",
    "Why Diesel Has Become a Much Bigger Economic Problem Than Gasoline": "柴油價格與供需問題對經濟的衝擊正大於汽油",
    "What to know if your flight is canceled amid rising jet fuel costs": "航油成本上升導致航班取消時，旅客應注意的事項",
    "The Dutch village at risk of being demolished": "荷蘭村莊可能因大型變電站建設面臨拆遷",
}


KEYWORD_TRANSLATIONS = (
    ("bullish", "多方"),
    ("bearish", "空方"),
    ("neutral", "中性"),
    ("IFVG", "反轉型公平價值缺口"),
    ("FVG", "公平價值缺口"),
    ("1H", "1 小時"),
    ("5M", "5 分鐘"),
    ("AI", "人工智慧"),
    ("Fed", "聯準會"),
    ("White House", "白宮"),
    ("justice department", "司法部"),
    ("sanctions", "制裁"),
    ("China", "中國"),
    ("oil", "石油"),
    ("EV", "電動車"),
    ("FDA", "美國食品藥物管理局"),
    ("Trump", "川普"),
)


def zh_text(text: str) -> str:
    clean = " ".join(str(text).split())
    if not clean:
        return ""
    if clean in TITLE_TRANSLATIONS:
        return TITLE_TRANSLATIONS[clean]
    mixed = _replace_keywords(clean)
    if mixed != clean:
        clean = mixed
    if not _looks_english(clean):
        return clean
    translated = _replace_keywords(clean)
    if translated != clean and _has_cjk(translated):
        return f"外媒報導：{translated}"
    return "外媒新聞：此題材與產業訊號相關，已納入觀察"


def _replace_keywords(text: str) -> str:
    translated = text
    for source, target in KEYWORD_TRANSLATIONS:
        translated = re.sub(re.escape(source), target, translated, flags=re.IGNORECASE)
    return translated


def _looks_english(text: str) -> bool:
    letters = sum(char.isascii() and char.isalpha() for char in text)
    return letters >= max(8, len(text) * 0.35)


def _has_cjk(text: str) -> bool:
    return any("\u4e00" <= char <= "\u9fff" for char in text)
