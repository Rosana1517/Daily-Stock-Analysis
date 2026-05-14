from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class AiSupplyChainProfile:
    category: str
    score: int
    tier: str
    reason: str
    market_mainline: bool


AI_CORE_SUPPLY_CHAIN: dict[str, AiSupplyChainProfile] = {
    "2330": AiSupplyChainProfile("CoWoS / 先進封裝 / AI晶圓代工", 55, "Tier 1", "AI GPU/ASIC 先進製程與 CoWoS 平台核心。", True),
    "2454": AiSupplyChainProfile("AI ASIC / Edge AI晶片設計", 35, "Tier 1", "ASIC 與 AI 終端晶片設計受惠，屬算力晶片設計支線。", True),
    "3661": AiSupplyChainProfile("AI ASIC 設計服務", 30, "Tier 1", "客製化 ASIC 設計服務，與雲端 AI 加速器需求直接相關。", True),
    "3443": AiSupplyChainProfile("AI ASIC 設計服務", 30, "Tier 1", "先進製程 ASIC 設計服務，直接受惠雲端 AI 晶片開案。", True),
    "5274": AiSupplyChainProfile("AI Server 管理晶片", 30, "Tier 1", "伺服器 BMC/管理晶片，AI server 平台滲透率高。", True),
    "6643": AiSupplyChainProfile("高速介面 IP / ASIC IP", 30, "Tier 1", "高速介面與先進製程 IP，支援 AI ASIC 設計。", True),
    "6531": AiSupplyChainProfile("HBM / 記憶體介面", 25, "Tier 1", "高頻寬記憶體與先進記憶體介面相關。", True),
    "3529": AiSupplyChainProfile("ASIC IP / 矽智財", 30, "Tier 1", "矽智財授權與先進晶片設計流程相關。", True),
    "3711": AiSupplyChainProfile("先進封裝 / 封測", 25, "Tier 1", "封測平台受惠 AI 晶片先進封裝與高階測試需求。", True),
    "6239": AiSupplyChainProfile("HBM / 高階封測", 25, "Tier 1", "記憶體封測與高階封裝需求受惠。", True),
    "2449": AiSupplyChainProfile("AI 晶片測試", 25, "Tier 1", "高階晶片測試需求與 AI/HPC 晶片量產連動。", True),
    "3264": AiSupplyChainProfile("AI 晶片測試", 25, "Tier 1", "晶圓測試與高階半導體測試需求受惠。", True),
    "6510": AiSupplyChainProfile("高速測試介面", 25, "Tier 1", "探針卡/測試介面受惠 AI 晶片測試規格升級。", True),
    "6223": AiSupplyChainProfile("高速測試介面", 25, "Tier 1", "探針卡與測試介面為高階晶片測試關鍵。", True),
    "6515": AiSupplyChainProfile("高速測試介面", 25, "Tier 1", "測試座與高階測試介面受惠 AI 晶片量產。", True),
    "3131": AiSupplyChainProfile("CoWoS 設備", 25, "Tier 1", "濕製程/先進封裝設備，CoWoS 擴產受惠。", True),
    "3583": AiSupplyChainProfile("CoWoS 設備", 25, "Tier 1", "半導體與先進封裝設備，CoWoS 擴產受惠。", True),
    "6187": AiSupplyChainProfile("CoWoS 設備", 25, "Tier 1", "封裝與自動化設備，受惠先進封裝投資。", True),
    "2467": AiSupplyChainProfile("CoWoS / PCB 製程設備", 25, "Tier 1", "光熱製程設備切入半導體先進封裝與高階 PCB。", True),
    "6640": AiSupplyChainProfile("先進封裝設備", 25, "Tier 1", "封裝檢測與設備受惠先進封裝擴產。", True),
    "5443": AiSupplyChainProfile("先進封裝設備", 25, "Tier 1", "研磨、檢測與半導體設備切入先進封裝。", True),
    "6532": AiSupplyChainProfile("CoWoS 廠務/設備支援", 25, "Tier 1", "先進封裝廠務與設備支援供應鏈。", True),
    "6208": AiSupplyChainProfile("CoWoS 廠務設備", 25, "Tier 1", "半導體設備與廠務系統受惠 CoWoS 擴產。", True),
    "6691": AiSupplyChainProfile("Datacenter / CoWoS 廠務工程", 25, "Tier 1", "高階廠務工程，受惠先進封裝與資料中心建置。", True),
    "1717": AiSupplyChainProfile("先進封裝材料", 25, "Tier 1", "電子材料切入先進封裝與矽光子材料鏈。", False),
    "2382": AiSupplyChainProfile("AI Server ODM", 20, "Tier 1", "AI server 整機與雲端客戶供應鏈主力。", True),
    "3231": AiSupplyChainProfile("AI Server ODM", 20, "Tier 1", "AI server 整機代工與雲端客戶需求直接相關。", True),
    "6669": AiSupplyChainProfile("AI Server ODM", 20, "Tier 1", "雲端資料中心伺服器與 AI server 主力供應商。", True),
    "2356": AiSupplyChainProfile("AI Server ODM", 20, "Tier 1", "伺服器代工業務受惠 AI server 滲透。", True),
    "2317": AiSupplyChainProfile("AI Server ODM/OEM", 20, "Tier 1", "AI server 與資料中心整機組裝供應鏈。", True),
    "2324": AiSupplyChainProfile("AI Server ODM", 20, "Tier 1", "伺服器 ODM 受惠 AI server 需求。", False),
    "3706": AiSupplyChainProfile("AI Server ODM", 20, "Tier 1", "伺服器平台與 AI server 需求連動。", False),
    "2376": AiSupplyChainProfile("AI Server / AI PC", 20, "Tier 1", "AI server 系統與 AI PC 產品線並行。", False),
    "8210": AiSupplyChainProfile("AI Server 機殼/機櫃", 20, "Tier 1", "高階伺服器機殼與機櫃供應鏈。", True),
    "3693": AiSupplyChainProfile("AI Server 系統整合", 20, "Tier 1", "工業伺服器與高階運算系統整合。", False),
    "3017": AiSupplyChainProfile("AI GPU 散熱 / 液冷", 15, "Tier 2", "冷板、CDU、散熱模組，AI server 液冷主線。", True),
    "3324": AiSupplyChainProfile("AI GPU 散熱 / 液冷", 15, "Tier 2", "冷板、均熱板與液冷模組，受惠 AI server 熱設計升級。", True),
    "3653": AiSupplyChainProfile("AI GPU 散熱 / IHS", 15, "Tier 2", "高階散熱零組件與伺服器熱管理供應鏈。", True),
    "2421": AiSupplyChainProfile("AI Server 風扇 / 液冷", 15, "Tier 2", "風扇、水冷與伺服器散熱系統。", True),
    "6230": AiSupplyChainProfile("AI Server 散熱模組", 15, "Tier 2", "熱導管、均熱板與伺服器散熱模組。", False),
    "8996": AiSupplyChainProfile("AI GPU 散熱 / 液冷", 15, "Tier 2", "熱交換與液冷相關零組件。", True),
    "6805": AiSupplyChainProfile("液冷快接頭 / 機構件", 15, "Tier 2", "伺服器液冷快接頭與高階機構件受惠。", True),
    "3483": AiSupplyChainProfile("AI Server 散熱", 15, "Tier 2", "散熱模組與伺服器熱管理供應鏈。", False),
    "3037": AiSupplyChainProfile("ABF / 高速PCB", 10, "Tier 2", "ABF 載板與高階 PCB 受惠 AI 晶片與 AI server。", True),
    "3189": AiSupplyChainProfile("ABF 載板", 10, "Tier 2", "ABF 載板受惠高階 GPU/ASIC 封裝基板需求。", True),
    "8046": AiSupplyChainProfile("ABF 載板", 10, "Tier 2", "ABF 載板與高階封裝基板供應鏈。", True),
    "2368": AiSupplyChainProfile("AI PCB", 10, "Tier 2", "AI server 高層數 PCB 受惠。", True),
    "2383": AiSupplyChainProfile("AI PCB / CCL", 10, "Tier 2", "高速 CCL 材料為 AI server PCB 關鍵。", True),
    "6274": AiSupplyChainProfile("AI PCB / CCL", 10, "Tier 2", "低損耗高速材料受惠 AI server 與高速網通。", True),
    "6213": AiSupplyChainProfile("AI PCB / CCL", 10, "Tier 2", "高速 CCL 供應鏈，受惠 AI server 材料升級。", True),
    "4958": AiSupplyChainProfile("AI PCB", 10, "Tier 2", "高階 PCB 受惠 AI server 與資料中心需求。", False),
    "2313": AiSupplyChainProfile("AI PCB", 10, "Tier 2", "高階 PCB 與伺服器板供應鏈。", False),
    "5469": AiSupplyChainProfile("AI PCB", 10, "Tier 2", "高階 PCB 受惠資料中心設備需求。", False),
    "8155": AiSupplyChainProfile("AI PCB", 10, "Tier 2", "高階 PCB 與伺服器應用受惠。", False),
    "3081": AiSupplyChainProfile("AI 光通訊 / Silicon Photonics", 10, "Tier 2", "高速雷射與光通訊元件，受惠 AI data center 網路升級。", True),
    "6442": AiSupplyChainProfile("AI 光通訊 / CPO", 10, "Tier 2", "光通訊元件與高速資料中心網路升級。", True),
    "3163": AiSupplyChainProfile("AI 光通訊", 10, "Tier 2", "光收發模組與 AI data center 網路需求相關。", True),
    "4979": AiSupplyChainProfile("AI 光通訊", 10, "Tier 2", "光通訊元件受惠 AI data center 高速連線需求。", True),
    "3450": AiSupplyChainProfile("AI 光通訊", 10, "Tier 2", "高速光通訊元件供應鏈。", False),
    "4908": AiSupplyChainProfile("AI 光通訊", 10, "Tier 2", "光通訊設備受惠資料中心網路建置。", False),
    "3363": AiSupplyChainProfile("AI 光通訊", 10, "Tier 2", "光纖與光通訊元件受惠資料中心互連。", False),
    "3234": AiSupplyChainProfile("AI 光通訊", 10, "Tier 2", "光通訊元件供應鏈。", False),
    "2308": AiSupplyChainProfile("AI 電源 / Datacenter", 10, "Tier 2", "伺服器電源、電力管理與資料中心基礎設施。", True),
    "2301": AiSupplyChainProfile("AI 電源", 10, "Tier 2", "AI server 電源與資料中心電源模組。", True),
    "3015": AiSupplyChainProfile("AI 電源", 10, "Tier 2", "伺服器電源供應器受惠 AI server 功耗提升。", False),
    "6282": AiSupplyChainProfile("AI 電源", 10, "Tier 2", "電源供應器與資料中心電源需求相關。", False),
    "3211": AiSupplyChainProfile("BBU / 電池模組", 10, "Tier 2", "電池備援與伺服器/資料中心 BBU 需求相關。", False),
    "4931": AiSupplyChainProfile("BBU / 電池模組", 10, "Tier 2", "高功率電池模組與備援電力供應鏈。", False),
    "6781": AiSupplyChainProfile("BBU / 電池模組", 10, "Tier 2", "資料中心與伺服器備援電池模組。", False),
    "6412": AiSupplyChainProfile("AI 電源", 10, "Tier 2", "伺服器電源與高功率電源供應鏈。", False),
    "2404": AiSupplyChainProfile("AI Datacenter 廠務", 10, "Tier 2", "半導體廠務與資料中心建置工程。", True),
    "5536": AiSupplyChainProfile("AI Datacenter 廠務", 10, "Tier 2", "高科技廠房與資料中心工程受惠。", True),
    "6139": AiSupplyChainProfile("AI Datacenter 廠務", 10, "Tier 2", "高科技廠房與資料中心建置供應鏈。", True),
    "2345": AiSupplyChainProfile("AI Datacenter 網通", 10, "Tier 2", "高速交換器與 AI data center 網路設備。", True),
    "3665": AiSupplyChainProfile("高速線束 / Datacenter", 10, "Tier 2", "高速互連線束與資料中心設備供應鏈。", False),
    "5269": AiSupplyChainProfile("高速介面晶片", 10, "Tier 2", "高速介面晶片受惠 AI server I/O 規格升級。", False),
    "2357": AiSupplyChainProfile("AI PC / Edge AI", 5, "Tier 3", "AI PC 與邊緣 AI 受惠，非算力核心主線。", False),
    "2377": AiSupplyChainProfile("AI PC / Edge AI", 5, "Tier 3", "AI PC 與邊緣 AI 受惠，非算力核心主線。", False),
}


def ai_profile_for(symbol: str) -> AiSupplyChainProfile | None:
    return AI_CORE_SUPPLY_CHAIN.get(str(symbol).strip())
