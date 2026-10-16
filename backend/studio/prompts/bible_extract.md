忠实整理人物 characters、场景 locations、道具 props 三张表。只列原文出现或明确提及的项，未出现的表使用空数组；description 只记录原文事实，不设计未写出的外貌。
人物包含 name、role、description、appearance_status、appearance_excerpt。
如果原文明确写了该人物的外形，appearance_status 为 from_text，appearance_excerpt 必须逐字摘录原文里连续的一段外形描写，不能总结、扩写、加省略号或拼接。
如果原文没写外形，appearance_status 必须是 needs_author，appearance_excerpt 必须是空字符串。不得编造年龄、性别、服装、五官、发型、体型等信息；让作者在后续定妆时补充。
场景和道具各包含 name 与 description；人物关系或道具用途没有交代时写“原文未交代”。
