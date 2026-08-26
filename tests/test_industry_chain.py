from __future__ import annotations

import unittest

from stock_signal_system.data.industry_chain import (
    ChainConsensusGroup,
    IndustryChainMember,
    find_chain_consensus_groups,
    parse_industry_chain_html,
)

# Minimal fixtures mirroring the real markup observed on ic.tpex.org.tw's
# introduce.php?ic=... pages (see PRD.md P8), trimmed to the parts the parser
# actually reads.
_TWO_TIER_HTML = """
<div id="main_ic_panel" class="chain-panel">
    <div class="chain">
        <div class="chain-title-panel">上游</div>
        <div class="chain-company">
            <div id="ic_link_I100" class="company-chain-panel">網路IC</div>
            <div id="ic_link_I200" class="company-chain-panel">微處理器</div>
        </div>
    </div>
    <div class="blockchain"></div>
    <div class="chain">
        <div class="chain-title-panel">下游</div>
        <div class="chain-company">
            <div id="ic_link_IA00" class="company-chain-panel">網路設備</div>
        </div>
    </div>
</div>
<div id="companyList_I100" title="網路IC" class="x-hidden"><div class="company-list"><table><tr>
<td class='company'><a href="company_basic.php?stk_code=2459" class="company-text-over" title="敦吉">敦吉</a></td>
<td class="company"><a href="company_basic.php?stk_code=3169" class="company-text-over" title="亞信">亞信</a></td>
<td class="company"><a href="http://www.intel.com" class="company-text-over" title="英特爾" target="_blank">英特爾</a></td>
</tr></table></div><span class="company-number">共3家</span></div>
<div id="companyList_I200" title="微處理器" class="x-hidden"><div class="company-list"><table><tr>
<td class='company'><a href="company_basic.php?stk_code=6470" class="company-text-over" title="宇智">宇智</a></td>
</tr></table></div><span class="company-number">共1家</span></div>
<div id="companyList_IA00" title="網路設備" class="x-hidden"><div class="company-list"><table><tr>
<td class='company'><a href="company_basic.php?stk_code=2345" class="company-text-over" title="智易">智易</a></td>
</tr></table></div><span class="company-number">共1家</span></div>
"""

_THREE_TIER_HTML = """
<div id="main_ic_panel" class="chain-panel">
    <div class="chain">
        <div class="chain-title-panel">上游</div>
        <div class="chain-company">
            <div id="ic_link_DC00" class="company-chain-panel">IP設計<br/>/IC設計<br/>代工服務</div>
            <div id="ic_link_D100" class="company-chain-panel">IC設計</div>
        </div>
    </div>
    <div class="blockchain"></div>
    <div class="chain">
        <div class="chain-title-panel">中游</div>
        <div class="chain-company">
            <div id="ic_link_D300" class="company-chain-panel">IC/晶圓製造</div>
        </div>
    </div>
    <div class="blockchain"></div>
    <div class="chain">
        <div class="chain-title-panel">下游</div>
        <div class="chain-company">
            <div id="ic_link_D900" class="company-chain-panel">IC封裝測試</div>
        </div>
    </div>
</div>
<div id="companyList_DC00" title="IP設計/IC設計代工服務" class="x-hidden"><div class="company-list"><table><tr>
<td class='company'><a href="company_basic.php?stk_code=3443" class="company-text-over" title="創意">創意</a></td>
</tr></table></div></div>
<div id="companyList_D100" title="IC設計" class="x-hidden"><div class="company-list"><table><tr>
<td class='company'><a href="company_basic.php?stk_code=2454" class="company-text-over" title="聯發科">聯發科</a></td>
</tr></table></div></div>
<div id="companyList_D300" title="IC/晶圓製造" class="x-hidden"><div class="company-list"><table><tr>
<td class='company'><a href="company_basic.php?stk_code=2330" class="company-text-over" title="台積電">台積電</a></td>
</tr></table></div></div>
<div id="companyList_D900" title="IC封裝測試" class="x-hidden"><div class="company-list"><table><tr>
<td class='company'><a href="company_basic.php?stk_code=2311" class="company-text-over" title="日月光投控">日月光投控</a></td>
</tr></table></div></div>
"""


class ParseIndustryChainHtmlTest(unittest.TestCase):
    def test_two_tier_page_assigns_correct_tiers(self):
        members = parse_industry_chain_html(_TWO_TIER_HTML, "I000")
        by_code = {member.stock_code: member for member in members}
        self.assertEqual(by_code["2459"].tier, "上游")
        self.assertEqual(by_code["2459"].subcategory_name, "網路IC")
        self.assertEqual(by_code["6470"].tier, "上游")
        self.assertEqual(by_code["2345"].tier, "下游")
        self.assertEqual(by_code["2345"].subcategory_name, "網路設備")

    def test_foreign_company_without_stk_code_is_excluded(self):
        members = parse_industry_chain_html(_TWO_TIER_HTML, "I000")
        codes = {member.stock_code for member in members}
        self.assertNotIn("英特爾", codes)
        self.assertEqual(len(members), 4)

    def test_ic_code_is_stamped_on_every_member(self):
        members = parse_industry_chain_html(_TWO_TIER_HTML, "I000")
        self.assertTrue(all(member.ic_code == "I000" for member in members))

    def test_three_tier_page_assigns_all_three_tiers(self):
        members = parse_industry_chain_html(_THREE_TIER_HTML, "D000")
        by_code = {member.stock_code: member for member in members}
        self.assertEqual(by_code["3443"].tier, "上游")
        self.assertEqual(by_code["2454"].tier, "上游")
        self.assertEqual(by_code["2330"].tier, "中游")
        self.assertEqual(by_code["2311"].tier, "下游")

    def test_br_tags_in_subcategory_name_are_joined_cleanly(self):
        members = parse_industry_chain_html(_THREE_TIER_HTML, "D000")
        by_code = {member.stock_code: member for member in members}
        self.assertEqual(by_code["3443"].subcategory_name, "IP設計/IC設計代工服務")

    def test_empty_html_returns_no_members(self):
        self.assertEqual(parse_industry_chain_html("", "X000"), ())

    def test_duplicated_company_list_block_is_deduplicated(self):
        # Mirrors a real quirk observed on ic.tpex.org.tw: the same
        # companyList_{code} block (and hence the same <a stk_code=...>) can
        # appear more than once in one page fetch. A stock should only be
        # counted once per subcategory, not once per repeated appearance.
        duplicated_html = _TWO_TIER_HTML + _TWO_TIER_HTML
        members = parse_industry_chain_html(duplicated_html, "I000")
        matching = [member for member in members if member.stock_code == "2459"]
        self.assertEqual(len(matching), 1)


class FindChainConsensusGroupsTest(unittest.TestCase):
    def setUp(self):
        self.index = {
            "2459": (IndustryChainMember("2459", "敦吉", "I000", "上游", "I100", "網路IC"),),
            "6470": (IndustryChainMember("6470", "宇智", "I000", "上游", "I200", "微處理器"),),
            "2345": (IndustryChainMember("2345", "智易", "I000", "下游", "IA00", "網路設備"),),
            "2454": (IndustryChainMember("2454", "聯發科", "D000", "上游", "D100", "IC設計"),),
        }

    def test_two_signaling_stocks_in_same_tier_form_a_consensus_group(self):
        groups = find_chain_consensus_groups({"2459": "敦吉", "6470": "宇智"}, self.index)
        self.assertEqual(groups, (ChainConsensusGroup("I000", "上游", (("2459", "敦吉"), ("6470", "宇智"))),))

    def test_single_signaling_stock_does_not_meet_threshold(self):
        groups = find_chain_consensus_groups({"2345": "智易"}, self.index)
        self.assertEqual(groups, ())

    def test_signals_in_different_tiers_do_not_combine(self):
        groups = find_chain_consensus_groups({"2459": "敦吉", "2345": "智易"}, self.index)
        self.assertEqual(groups, ())

    def test_stock_missing_from_index_is_ignored_without_error(self):
        groups = find_chain_consensus_groups({"9999": "不存在"}, self.index)
        self.assertEqual(groups, ())

    def test_no_signaling_symbols_returns_empty(self):
        self.assertEqual(find_chain_consensus_groups({}, self.index), ())

    def test_custom_min_members_threshold(self):
        groups = find_chain_consensus_groups({"2345": "智易"}, self.index, min_members=1)
        self.assertEqual(groups, (ChainConsensusGroup("I000", "下游", (("2345", "智易"),)),))


if __name__ == "__main__":
    unittest.main()
