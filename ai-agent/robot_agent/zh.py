"""Simplified -> Traditional Chinese for single characters the local model
sometimes mixes into its answers (「现在」「正确」). Only characters that are
never correct in Traditional Chinese are mapped, so Traditional text is left
unchanged. Used by the team's reporter (code, not the model)."""

S2T = str.maketrans(
    "们这说运场关键结车辆为过时检测么问题个对没还发现样经进让门实应该数据显执败续员态览较"
    "动东边体离机摆将从处无范围远务两会请给记录认识别吗当见觉开书写号简单节点线极标达选择"
    "设计划举丢头种类错误亿万与并级际区尽虽难须满腾换调试话语词释视观规则预报输赢确现块"
    "转钟间题图层终于产业务专传伤价优们备复够头夹层带张弹径总惯户择挡损据携摄撑来权条杂"
    "杨极构枪柜样桥检欢残毕气汇汉沟没泽测济浅涂润涨滚潜灯灵灾炉烟热爱牵状犹独猎环现",
    "們這說運場關鍵結車輛為過時檢測麼問題個對沒還發現樣經進讓門實應該數據顯執敗續員態覽較"
    "動東邊體離機擺將從處無範圍遠務兩會請給記錄認識別嗎當見覺開書寫號簡單節點線極標達選擇"
    "設計劃舉丟頭種類錯誤億萬與並級際區盡雖難須滿騰換調試話語詞釋視觀規則預報輸贏確現塊"
    "轉鐘間題圖層終於產業務專傳傷價優們備復夠頭夾層帶張彈徑總慣戶擇擋損據攜攝撐來權條雜"
    "楊極構槍櫃樣橋檢歡殘畢氣匯漢溝沒澤測濟淺塗潤漲滾潛燈靈災爐煙熱愛牽狀猶獨獵環現")


def to_traditional(text: str) -> str:
    return text.translate(S2T)
