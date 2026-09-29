"""Builds report_rules.json (the Compare-tab / PDF advice rules). Edit here, then:

    python3 build_rules.py report_rules.json
    pytest tests/test_report_insights.py      # from v3/backend

See README.md for the metrics, placeholders and how rules are picked.
"""
import json, sys

RULES = []


def R(id, section, modes, group, when, priority, title, bullets_th, bullets_en, reason_th, reason_en):
    RULES.append({
        'id': id, 'section': section, 'modes': modes, 'group': group,
        'title': {'th': title[0], 'en': title[1]},
        'when': when, 'priority': priority,
        'bullets': {'th': bullets_th, 'en': bullets_en},
        'reason': {'th': reason_th, 'en': reason_en},
    })


L, T, E = ['location'], ['tenant'], ['tag']
LT = ['location', 'tenant']

# ============================== shared trend / data rules ==============================
UP_WHEN = "has_prev and prev_kg >= 5 and change_pct >= 15"
UP_PRIO = "60 + min(change_pct, 100) * 0.3"
UP_REASON_TH = "ขยะรวม {cur_kg:kg} เทียบกับ {prev_kg:kg} ในช่วง {prev_label} เพิ่มขึ้น {change_pct:pct} ซึ่งเป็นการเพิ่มขึ้นที่ชัดเจน จึงควรหาสาเหตุก่อนที่จะกลายเป็นแนวโน้มต่อเนื่อง"
UP_REASON_EN = "{cur_kg:kg} this period against {prev_kg:kg} for {prev_label}: up {change_pct:pct}, a clear rise worth explaining before it becomes a trend."

R('L-R01', 'risk', L, 'trend', UP_WHEN, UP_PRIO,
  ("ปริมาณขยะเพิ่มขึ้นจาก{compare_word}", "Waste is up on {compare_word}"),
  ["ขยะช่วง {cur_label} เพิ่มขึ้น {change_pct:pct} เมื่อเทียบกับช่วง {prev_label}",
   "ค่าจัดเก็บและกำจัดขยะของอาคารจะเพิ่มขึ้นตามปริมาณ",
   "ตรวจสอบพื้นที่หรือผู้ใช้อาคารที่ขยะเพิ่มขึ้น และกิจกรรมพิเศษในช่วงนี้"],
  ["Waste for {cur_label} is up {change_pct:pct} on {prev_label}",
   "The building's collection and disposal costs rise with volume",
   "Find the areas or occupants behind the increase, and any one-off events"],
  UP_REASON_TH, UP_REASON_EN)
R('T-R01', 'risk', T, 'trend', UP_WHEN, UP_PRIO,
  ("ขยะของผู้เช่าเพิ่มขึ้นจาก{compare_word}", "Your waste is up on {compare_word}"),
  ["ขยะช่วง {cur_label} เพิ่มขึ้น {change_pct:pct} เมื่อเทียบกับช่วง {prev_label}",
   "ตรวจสอบกิจกรรมในสำนักงานที่เพิ่มขึ้น เช่น การประชุม การสั่งอาหาร หรือพนักงานที่เพิ่มขึ้น",
   "ตั้งเป้าลดขยะร่วมกันในทีมสำหรับเดือนถัดไป"],
  ["Waste for {cur_label} is up {change_pct:pct} on {prev_label}",
   "Look for what changed in the office: meetings, food orders, headcount",
   "Set a shared team target to bring it down next month"],
  UP_REASON_TH, UP_REASON_EN)
R('E-R01', 'risk', E, 'trend', UP_WHEN, UP_PRIO,
  ("ขยะจากกิจกรรม/พื้นที่เพิ่มขึ้นจาก{compare_word}", "Waste from these events/areas is up on {compare_word}"),
  ["ขยะช่วง {cur_label} เพิ่มขึ้น {change_pct:pct} เมื่อเทียบกับช่วง {prev_label}",
   "ตรวจสอบว่ามาจากจำนวนผู้เข้าร่วม จำนวนกิจกรรม หรือรูปแบบการจัดที่เปลี่ยนไป",
   "วางแผนจุดทิ้งและการคัดแยกให้พอกับขนาดงานครั้งถัดไป"],
  ["Waste for {cur_label} is up {change_pct:pct} on {prev_label}",
   "Check whether attendance, the number of events or the format changed",
   "Size bins and sorting stations to match the next event"],
  UP_REASON_TH, UP_REASON_EN)

R('L-R02', 'risk', L, 'trend', "consecutive_increase_months >= 3", "70 + consecutive_increase_months * 3",
  ("ขยะเพิ่มขึ้นต่อเนื่องหลายเดือน", "Waste has risen several months in a row"),
  ["ปริมาณขยะต่อวันเพิ่มขึ้นติดต่อกัน {consecutive_increase_months:int} เดือน",
   "หากไม่ปรับเปลี่ยน ต้นทุนและผลกระทบของอาคารจะสูงขึ้นต่อเนื่อง",
   "กำหนดเป้าหมายลดขยะรายเดือนและติดตามผลทุกเดือน"],
  ["Waste per day has grown {consecutive_increase_months:int} months in a row",
   "Left alone, the building's costs and impact keep climbing",
   "Set a monthly reduction target and review it every month"],
  "ปริมาณขยะเฉลี่ยต่อวันเพิ่มขึ้นทุกเดือนติดต่อกัน {consecutive_increase_months:int} เดือนจนถึงเดือนล่าสุด จึงเป็นแนวโน้มต่อเนื่อง ไม่ใช่ความผันผวนเดือนเดียว",
  "Average waste per day rose every month for {consecutive_increase_months:int} months up to the latest month, a sustained trend rather than a one-month blip.")
R('T-R02', 'risk', T, 'trend', "consecutive_increase_months >= 3", "70 + consecutive_increase_months * 3",
  ("ขยะของผู้เช่าเพิ่มขึ้นต่อเนื่อง", "Your waste has risen several months in a row"),
  ["ปริมาณขยะต่อวันเพิ่มขึ้นติดต่อกัน {consecutive_increase_months:int} เดือน",
   "ทบทวนพฤติกรรมที่ทำให้เกิดขยะในสำนักงานร่วมกับทีม",
   "ตั้งเป้าหมายลดขยะรายเดือนและแจ้งผลให้ทีมทราบ"],
  ["Waste per day has grown {consecutive_increase_months:int} months in a row",
   "Review with the team what creates waste in the office",
   "Set a monthly target and share progress with the team"],
  "ปริมาณขยะเฉลี่ยต่อวันเพิ่มขึ้นทุกเดือนติดต่อกัน {consecutive_increase_months:int} เดือนจนถึงเดือนล่าสุด จึงเป็นแนวโน้มต่อเนื่อง",
  "Average waste per day rose every month for {consecutive_increase_months:int} months up to the latest month, a sustained trend.")

GEN_UP_WHEN = "general_has_prev and general_prev_kg >= 3 and general_change_pct >= 20"
GEN_UP_PRIO = "55 + min(general_change_pct, 100) * 0.3"
GEN_UP_REASON_TH = "ขยะทั่วไป {general_cur_kg:kg} เทียบกับ {general_prev_kg:kg} ในช่วง {prev_label} เพิ่มขึ้น {general_change_pct:pct} ขยะส่วนนี้ส่วนใหญ่ไม่ได้ถูกนำกลับมาใช้ประโยชน์"
GEN_UP_REASON_EN = "General waste was {general_cur_kg:kg} against {general_prev_kg:kg} for {prev_label}, up {general_change_pct:pct}; most of it is never recovered."
R('L-R03', 'risk', L, 'general_trend', GEN_UP_WHEN, GEN_UP_PRIO,
  ("ขยะทั่วไป (ส่งฝังกลบ) เพิ่มขึ้น", "General (landfill) waste is rising"),
  ["ขยะทั่วไปเพิ่มขึ้น {general_change_pct:pct} จาก{compare_word}",
   "เพิ่มทั้งค่าฝังกลบและก๊าซเรือนกระจกของอาคาร",
   "สุ่มตรวจถังขยะทั่วไปว่ามีวัสดุรีไซเคิลหรือเศษอาหารปนอยู่มากแค่ไหน"],
  ["General waste is up {general_change_pct:pct} on {compare_word}",
   "It raises both landfill fees and the building's emissions",
   "Spot-check general bins for recyclables and food scraps"],
  GEN_UP_REASON_TH, GEN_UP_REASON_EN)
R('T-R03', 'risk', T, 'general_trend', GEN_UP_WHEN, GEN_UP_PRIO,
  ("ขยะทั่วไปของผู้เช่าเพิ่มขึ้น", "Your general waste is rising"),
  ["ขยะทั่วไปเพิ่มขึ้น {general_change_pct:pct} จาก{compare_word}",
   "ตรวจดูว่ามีกล่องอาหาร ขวด หรือกระดาษที่แยกได้ถูกทิ้งรวมหรือไม่",
   "ย้ำการแยกขยะกับทีมและผู้มาติดต่อ"],
  ["General waste is up {general_change_pct:pct} on {compare_word}",
   "Check for food boxes, bottles or paper that could have been sorted",
   "Remind the team and visitors how to sort"],
  GEN_UP_REASON_TH, GEN_UP_REASON_EN)

SORT_DOWN_WHEN = "has_prev and prev_kg >= 5 and total_kg >= 5 and diversion_change_pts <= -10"
SORT_DOWN_PRIO = "65 + min(-diversion_change_pts, 40)"
SORT_DOWN_REASON_TH = "สัดส่วนขยะรีไซเคิลและขยะอินทรีย์ต่อขยะทั้งหมด ลดจาก {diversion_pct_prev:pct} ในช่วง {prev_label} เหลือ {diversion_pct:pct} ({diversion_change_pts:pts}) แสดงว่าการคัดแยกแย่ลงอย่างชัดเจน"
SORT_DOWN_REASON_EN = "The recyclable + organic share fell from {diversion_pct_prev:pct} ({prev_label}) to {diversion_pct:pct} ({diversion_change_pts:pts}): sorting has clearly slipped."
R('L-R04', 'risk', L, 'sorting', SORT_DOWN_WHEN, SORT_DOWN_PRIO,
  ("การคัดแยกของอาคารแย่ลง", "The building's sorting is slipping"),
  ["สัดส่วนขยะที่คัดแยกได้ลดลงจาก {diversion_pct_prev:pct} เหลือ {diversion_pct:pct}",
   "วัสดุรีไซเคิลที่ปนในขยะทั่วไปจะเสียมูลค่าและต้องส่งกำจัด",
   "ตรวจจุดทิ้งขยะส่วนกลางและขั้นตอนการเก็บของแม่บ้าน"],
  ["The sorted share dropped from {diversion_pct_prev:pct} to {diversion_pct:pct}",
   "Recyclables mixed into general waste lose their value",
   "Check the shared bin stations and the housekeeping routine"],
  SORT_DOWN_REASON_TH, SORT_DOWN_REASON_EN)
R('T-R04', 'risk', T, 'sorting', SORT_DOWN_WHEN, SORT_DOWN_PRIO,
  ("การคัดแยกของผู้เช่าแย่ลง", "Your sorting is slipping"),
  ["สัดส่วนขยะที่คัดแยกได้ลดลงจาก {diversion_pct_prev:pct} เหลือ {diversion_pct:pct}",
   "ขยะที่ทิ้งผิดถังจะถูกนับเป็นขยะทั่วไปทั้งหมด",
   "ทบทวนวิธีคัดแยกกับทีมและตรวจว่าถังในสำนักงานยังครบ"],
  ["The sorted share dropped from {diversion_pct_prev:pct} to {diversion_pct:pct}",
   "Waste in the wrong bin all counts as general waste",
   "Refresh sorting with the team and check the office bins"],
  SORT_DOWN_REASON_TH, SORT_DOWN_REASON_EN)
R('E-R04', 'risk', E, 'sorting', SORT_DOWN_WHEN, SORT_DOWN_PRIO,
  ("การคัดแยกในกิจกรรม/พื้นที่แย่ลง", "Sorting at these events/areas is slipping"),
  ["สัดส่วนขยะที่คัดแยกได้ลดลงจาก {diversion_pct_prev:pct} เหลือ {diversion_pct:pct}",
   "จุดทิ้งที่ไม่ชัดเจนหรือไม่พอ ทำให้ผู้เข้าร่วมทิ้งรวม",
   "ทบทวนตำแหน่งและจำนวนจุดคัดแยกในครั้งถัดไป"],
  ["The sorted share dropped from {diversion_pct_prev:pct} to {diversion_pct:pct}",
   "Unclear or too few stations push people to bin everything together",
   "Review station placement and numbers for next time"],
  SORT_DOWN_REASON_TH, SORT_DOWN_REASON_EN)

GEN_HALF_WHEN = "total_kg >= 10 and general_pct >= 50"
GEN_HALF_PRIO = "50 + (general_pct - 50) * 0.8"
GEN_HALF_REASON_TH = "ขยะทั่วไป {general_kg:kg} จากขยะทั้งหมด {total_kg:kg} คิดเป็น {general_pct:pct} ซึ่งมากกว่าครึ่งหนึ่ง แสดงว่ายังมีวัสดุที่คัดแยกได้ปนอยู่ในขยะทั่วไปอีกมาก"
GEN_HALF_REASON_EN = "General waste is {general_kg:kg} of {total_kg:kg} ({general_pct:pct}), more than half, so a lot of sortable material is still going in the general bin."
R('L-R05', 'risk', L, 'sorting', GEN_HALF_WHEN, GEN_HALF_PRIO,
  ("ขยะทั่วไปของอาคารมีสัดส่วนเกินครึ่ง", "General waste is over half of the building's total"),
  ["ขยะทั่วไปคิดเป็น {general_pct:pct} ของขยะทั้งหมด",
   "ขยะส่วนนี้ส่วนใหญ่ถูกส่งฝังกลบ เพิ่มค่ากำจัดและก๊าซเรือนกระจก",
   "ทบทวนระบบถังและจุดคัดแยกในพื้นที่ส่วนกลาง รวมถึงเงื่อนไขกับผู้รับขยะ"],
  ["General waste is {general_pct:pct} of the total",
   "Most of it goes to landfill, adding cost and emissions",
   "Review the bin system in shared areas and the terms with your waste contractor"],
  GEN_HALF_REASON_TH, GEN_HALF_REASON_EN)
R('T-R05', 'risk', T, 'sorting', GEN_HALF_WHEN, GEN_HALF_PRIO,
  ("ขยะทั่วไปของผู้เช่ามีสัดส่วนเกินครึ่ง", "General waste is over half of your total"),
  ["ขยะทั่วไปคิดเป็น {general_pct:pct} ของขยะทั้งหมด",
   "กล่องอาหาร ขวด และกระดาษที่ทิ้งรวม ทำให้สัดส่วนนี้สูง",
   "เริ่มจากแยกเศษอาหารและขวดออกก่อน เพราะทำได้ง่ายที่สุด"],
  ["General waste is {general_pct:pct} of your total",
   "Food boxes, bottles and paper binned together push it up",
   "Start by pulling out food scraps and bottles, the easiest wins"],
  GEN_HALF_REASON_TH, GEN_HALF_REASON_EN)
R('E-R05', 'risk', E, 'sorting', GEN_HALF_WHEN, GEN_HALF_PRIO,
  ("ขยะจากกิจกรรมส่วนใหญ่เป็นขยะทั่วไป", "Most event waste is general waste"),
  ["ขยะทั่วไปคิดเป็น {general_pct:pct} ของขยะทั้งหมด",
   "ผู้เข้าร่วมมักทิ้งรวมเมื่อจุดทิ้งไม่ชัดเจนหรืออยู่ไกล",
   "วางจุดคัดแยกใกล้โซนอาหารและเครื่องดื่มพร้อมป้ายภาพ"],
  ["General waste is {general_pct:pct} of the total",
   "Attendees bin everything together when stations are unclear or far away",
   "Put sorting stations with picture signs next to food and drink areas"],
  GEN_HALF_REASON_TH, GEN_HALF_REASON_EN)

HAZ_REASON_TH = "พบขยะอันตราย {hazardous_kg:kg} ({hazardous_pct:pct} ของขยะทั้งหมด) ในช่วงนี้ ขยะอันตรายทุกปริมาณต้องจัดการแยกตามกฎหมาย แม้จะมีปริมาณน้อย"
HAZ_REASON_EN = "{hazardous_kg:kg} of hazardous waste ({hazardous_pct:pct} of the total) was recorded; any amount has to be handled separately under the regulations."
R('L-R07', 'risk', L, 'hazard', "hazardous_kg > 0", "68 + min(hazardous_pct, 30)",
  ("มีขยะอันตรายที่ต้องจัดการเป็นพิเศษ", "Hazardous waste needs special handling"),
  ["จัดพื้นที่เก็บขยะอันตรายที่ปิดมิดชิดและมีป้ายชัดเจน",
   "ส่งกำจัดผ่านผู้รับที่ได้รับอนุญาต พร้อมเก็บเอกสารการขนส่ง",
   "อบรมแม่บ้านและพนักงานทำความสะอาดให้แยกได้ถูกต้อง"],
  ["Set up a closed, clearly labelled hazardous-waste store",
   "Use licensed contractors and keep the transport documents",
   "Train housekeeping to separate it correctly"],
  HAZ_REASON_TH, HAZ_REASON_EN)
R('T-R07', 'risk', T, 'hazard', "hazardous_kg > 0", "68 + min(hazardous_pct, 30)",
  ("มีขยะอันตรายที่ต้องแยกเก็บ", "Hazardous waste must be kept separate"),
  ["แยกเก็บถ่าน หลอดไฟ และตลับหมึกไว้ในกล่องปิด",
   "แจ้งฝ่ายอาคารเพื่อส่งกำจัดตามช่องทางที่ถูกต้อง",
   "ห้ามทิ้งปนในถังขยะทั่วไป"],
  ["Keep batteries, lamps and toner cartridges in a closed box",
   "Ask building management to send them for proper disposal",
   "Never put them in the general bin"],
  HAZ_REASON_TH, HAZ_REASON_EN)
R('E-R07', 'risk', E, 'hazard', "hazardous_kg > 0", "68 + min(hazardous_pct, 30)",
  ("มีขยะอันตรายจากกิจกรรม/พื้นที่", "Hazardous waste at these events/areas"),
  ["เตรียมภาชนะแยกสำหรับถ่าน หลอดไฟ หรือกระป๋องสเปรย์",
   "แจ้งผู้จัดและทีมงานให้แยกเก็บก่อนส่งกำจัด",
   "ส่งต่อผู้รับกำจัดที่ได้รับอนุญาต"],
  ["Provide a separate container for batteries, lamps or aerosol cans",
   "Brief organisers and crew to keep them apart",
   "Hand them to a licensed disposal contractor"],
  HAZ_REASON_TH, HAZ_REASON_EN)

R('L-R08', 'risk', LT, 'hazard', "hazardous_has_prev and hazardous_prev_kg > 0 and hazardous_change_pct >= 20",
  "75 + min(hazardous_change_pct, 100) * 0.2",
  ("ขยะอันตรายเพิ่มขึ้น", "Hazardous waste is rising"),
  ["ขยะอันตรายเพิ่มขึ้น {hazardous_change_pct:pct} จาก{compare_word}",
   "เพิ่มความเสี่ยงด้านกฎหมายและความปลอดภัย",
   "ตรวจสอบแหล่งที่มา เช่น ถ่านไฟฉาย หลอดไฟ หรือสารเคมีทำความสะอาด"],
  ["Hazardous waste is up {hazardous_change_pct:pct} on {compare_word}",
   "It raises legal and safety risk",
   "Trace the source: batteries, lamps or cleaning chemicals"],
  "ขยะอันตราย {hazardous_cur_kg:kg} เทียบกับ {hazardous_prev_kg:kg} ในช่วง {prev_label} เพิ่มขึ้น {hazardous_change_pct:pct} ซึ่งเป็นหมวดที่ควรลดลง ไม่ใช่เพิ่มขึ้น",
  "Hazardous waste was {hazardous_cur_kg:kg} against {hazardous_prev_kg:kg} for {prev_label}, up {hazardous_change_pct:pct}, in a category that should be going down.")

R('L-R09', 'risk', ['location', 'tenant', 'tag'], 'biohazard', "bio_hazardous_kg > 0", "66",
  ("มีขยะติดเชื้อ", "Infectious waste found"),
  ["แยกใส่ถุงแดงและภาชนะที่ปิดมิดชิด",
   "ส่งกำจัดผ่านผู้รับขยะติดเชื้อที่ได้รับอนุญาต",
   "ห้ามปนกับขยะทั่วไปหรือขยะรีไซเคิล"],
  ["Bag it in red bags inside sealed containers",
   "Use a licensed infectious-waste contractor",
   "Never mix it with general or recyclable waste"],
  "พบขยะติดเชื้อ {bio_hazardous_kg:kg} ในช่วงนี้ ขยะประเภทนี้ต้องแยกจัดการตามข้อกำหนดด้านสาธารณสุขเสมอ",
  "{bio_hazardous_kg:kg} of infectious waste was recorded; it always has to be handled under public-health rules.")

R('L-R10', 'risk', ['location', 'tenant', 'tag'], 'contamination', "contaminated_plastic_kg >= 1 and contaminated_plastic_share >= 10",
  "45 + min(contaminated_plastic_share, 50) * 0.3",
  ("พลาสติกปนเปื้อนรีไซเคิลไม่ได้", "Contaminated plastic can't be recycled"),
  ["พลาสติกที่มีเศษอาหารหรือของเหลวติดอยู่มักถูกปฏิเสธการรับซื้อ",
   "ต้องส่งกำจัดแทนการรีไซเคิล เสียทั้งมูลค่าและค่าใช้จ่าย",
   "เทเศษอาหารและล้างบรรจุภัณฑ์ก่อนทิ้ง"],
  ["Plastic with food or liquid left in it is usually rejected by buyers",
   "It ends up disposed of instead of recycled",
   "Empty and rinse containers before binning them"],
  "พลาสติกปนเปื้อน {contaminated_plastic_kg:kg} คิดเป็น {contaminated_plastic_share:pct} ของพลาสติกทั้งหมด พลาสติกส่วนนี้ขายไม่ได้และทำให้พลาสติกที่สะอาดเสียราคาไปด้วย",
  "Contaminated plastic is {contaminated_plastic_kg:kg}, {contaminated_plastic_share:pct} of all plastic; it can't be sold and drags down the price of the clean plastic.")

STOP_REASON_TH = "บันทึกล่าสุดเมื่อ {last_record_date} ห่างจากวันสิ้นสุดข้อมูลของรายงาน {days_since_last_record:int} วัน ซึ่งนานกว่ารอบการชั่งปกติ ตัวเลขในรายงานจึงอาจต่ำกว่าความจริง"
STOP_REASON_EN = "The last record was on {last_record_date}, {days_since_last_record:int} days before the end of the report window, longer than a normal weighing cycle, so the figures may be understated."
R('L-R11', 'risk', L, 'data', "has_data and days_since_last_record >= 14", "58 + min(days_since_last_record, 60) * 0.3",
  ("ข้อมูลขยะไม่ได้บันทึกต่อเนื่อง", "Waste data has stopped coming in"),
  ["ไม่มีการบันทึกขยะมา {days_since_last_record:int} วัน",
   "ข้อมูลที่ขาดหายทำให้ปริมาณขยะและอัตรารีไซเคิลคลาดเคลื่อน",
   "ตรวจสอบว่าเครื่องชั่งและผู้บันทึกยังทำงานตามรอบปกติ"],
  ["No waste has been recorded for {days_since_last_record:int} days",
   "Missing data skews totals and the recycling rate",
   "Check the scales and the people recording still follow the schedule"],
  STOP_REASON_TH, STOP_REASON_EN)
R('T-R11', 'risk', T, 'data', "has_data and days_since_last_record >= 14", "58 + min(days_since_last_record, 60) * 0.3",
  ("ข้อมูลขยะของผู้เช่าไม่ได้บันทึกต่อเนื่อง", "Your waste data has stopped coming in"),
  ["ไม่มีการบันทึกขยะของผู้เช่ามา {days_since_last_record:int} วัน",
   "แจ้งฝ่ายอาคารหรือผู้ดูแลการชั่งว่าข้อมูลของผู้เช่าขาดหาย",
   "ตรวจว่าทีมยังนำขยะไปชั่งตามจุดที่กำหนด"],
  ["Nothing has been recorded for you for {days_since_last_record:int} days",
   "Let building management or the weighing team know your data is missing",
   "Check your team still takes waste to the weighing point"],
  STOP_REASON_TH, STOP_REASON_EN)

R('L-R12', 'risk', LT, 'data', "gap_months >= 1", "52 + gap_months * 2",
  ("มีเดือนที่ไม่มีข้อมูล", "Some months have no data"),
  ["ไม่มีการบันทึกขยะในเดือน {gap_month_labels}",
   "ยอดรวมทั้งช่วงและแนวโน้มรายเดือนจะคลาดเคลื่อน",
   "กรอกข้อมูลย้อนหลัง หรือระบุเหตุผลหากไม่มีขยะจริง"],
  ["Nothing was recorded in {gap_month_labels}",
   "Period totals and the monthly trend will be off",
   "Back-fill the data, or note why there was no waste"],
  "ในช่วงที่เลือกมี {gap_months:int} เดือนที่ไม่มีข้อมูลเลย ทั้งที่เดือนก่อนหน้าและถัดไปมีการบันทึก จึงน่าจะเป็นข้อมูลขาดมากกว่าไม่มีขยะจริง",
  "{gap_months:int} month(s) in the period have no records although the months around them do, which points to missing data rather than no waste.")

DROP_WHEN = "has_prev and prev_kg >= 10 and change_pct <= -60"
R('L-R13', 'risk', LT, 'data', DROP_WHEN, "57 + min(change_pct_abs, 100) * 0.1",
  ("ปริมาณขยะลดลงผิดปกติ", "Unusually sharp drop in waste"),
  ["ขยะช่วง {cur_label} ลดลง {change_pct_abs:pct} จาก{compare_word}",
   "อาจมาจากการบันทึกไม่ครบ หรือกิจกรรมในพื้นที่ลดลงจริง",
   "ตรวจสอบว่ามีจุดทิ้งขยะใดที่ยังไม่ได้ชั่งหรือบันทึก"],
  ["Waste for {cur_label} fell {change_pct_abs:pct} on {compare_word}",
   "Either recording is incomplete or activity really dropped",
   "Check for bin points that haven't been weighed or recorded"],
  "ขยะรวม {cur_kg:kg} เทียบกับ {prev_kg:kg} ในช่วง {prev_label} ลดลง {change_pct_abs:pct} การลดลงมากขนาดนี้ในช่วงสั้น ๆ มักมาจากข้อมูลที่บันทึกไม่ครบ จึงควรตรวจก่อนสรุปว่าลดขยะได้จริง",
  "{cur_kg:kg} against {prev_kg:kg} for {prev_label}, down {change_pct_abs:pct}. A drop this sharp usually means incomplete records, so check before calling it a real reduction.")

R('E-R14', 'risk', E, 'concentration', "group_count >= 2 and top_group_share >= 60", "55 + (top_group_share - 60) * 0.5",
  ("ขยะกระจุกอยู่ที่ {top_group_label}", "Waste is concentrated at {top_group_label}"),
  ["ขยะ {top_group_share:pct} มาจาก {top_group_label}",
   "ตรวจรูปแบบกิจกรรมหรือพื้นที่นี้ว่าทำไมขยะมาก",
   "เพิ่มจุดทิ้งและเจ้าหน้าที่ดูแลเฉพาะจุดนี้"],
  ["{top_group_share:pct} of the waste comes from {top_group_label}",
   "Look at why this event or area produces so much",
   "Add bins and staff support at this point"],
  "{top_group_label} มีขยะ {top_group_kg:kg} คิดเป็น {top_group_share:pct} ของทั้งหมดจาก {group_count:int} แท็ก การปรับปรุงที่จุดนี้จุดเดียวจึงให้ผลมากที่สุด",
  "{top_group_label} accounts for {top_group_kg:kg}, {top_group_share:pct} of the total across {group_count:int} tags, so improving this one point pays off most.")

# ============================== opportunities ==============================
def top_stream_reason(stream_th, stream_en, kg, pct, rank):
    return (f"{stream_th}เป็นขยะอันดับ {{{rank}:int}} ({{{kg}:kg}} หรือ {{{pct}:pct}} ของขยะทั้งหมด) จึงเป็นหมวดที่ลดหรือแยกแล้วเห็นผลมากที่สุด",
            f"{stream_en} is waste stream #{{{rank}:int}} ({{{kg}:kg}}, {{{pct}:pct}} of the total), so it's where reducing or sorting shows the biggest effect.")

rt, re_ = top_stream_reason("ขยะอินทรีย์และเศษอาหาร", "Organic/food waste", "organic_kg", "organic_pct", "organic_rank")
R('L-O01', 'opportunity', L, 'stream_organic', "organic_rank <= 3 and organic_pct >= 5", "45 + organic_pct",
  ("วางระบบจัดการขยะอินทรีย์ของอาคาร", "Set up organic-waste handling for the building"),
  ["จัดจุดรวมเศษอาหารแยกจากขยะทั่วไปในพื้นที่ส่วนกลางและศูนย์อาหาร",
   "หาคู่ค้ารับเศษอาหารไปทำปุ๋ยหรืออาหารสัตว์ หรือพิจารณาเครื่องย่อยเศษอาหาร",
   "เทียบค่าฝังกลบกับค่าจัดการขยะอินทรีย์เพื่อประเมินความคุ้มค่า"],
  ["Create food-scrap collection points in shared areas and food courts",
   "Find a compost or animal-feed partner, or consider a food digester",
   "Compare landfill fees with organic handling costs"],
  rt, re_)
R('T-O02', 'opportunity', T, 'stream_organic', "organic_rank <= 3 and organic_pct >= 5", "45 + organic_pct",
  ("แยกขยะอาหารในแพนทรี่", "Separate food waste in the pantry"),
  ["ตั้งถังเศษอาหารแยกในแพนทรี่และมุมทานอาหาร (ขอถังจากฝ่ายอาคารได้)",
   "เทน้ำและเศษอาหารออกจากกล่องก่อนทิ้ง เพื่อให้บรรจุภัณฑ์รีไซเคิลได้",
   "ลดอาหารเหลือจากการสั่งอาหารประชุมให้พอดีจำนวนคน"],
  ["Keep a separate food-scrap bin in the pantry (ask building management for one)",
   "Empty food and liquid from containers so the packaging can be recycled",
   "Order meeting food to headcount to cut leftovers"],
  rt, re_)
R('E-O01', 'opportunity', E, 'stream_organic', "organic_rank <= 3 and organic_pct >= 5", "45 + organic_pct",
  ("จัดการเศษอาหารจากกิจกรรม", "Handle food waste from events"),
  ["วางถังเศษอาหารแยกใกล้โซนอาหาร",
   "ตกลงกับผู้ให้บริการอาหารเรื่องปริมาณที่พอดีกับผู้เข้าร่วม",
   "ส่งอาหารเหลือที่ยังรับประทานได้ให้หน่วยงานรับบริจาค"],
  ["Put food-scrap bins next to food areas",
   "Agree portions with caterers to match attendance",
   "Donate edible surplus to food-rescue groups"],
  rt, re_)

rt, re_ = top_stream_reason("กระดาษ", "Paper", "paper_kg", "paper_pct", "paper_rank")
R('L-O03', 'opportunity', L, 'stream_paper', "paper_rank <= 3 and paper_pct >= 5", "45 + paper_pct",
  ("จัดโครงการเก็บกระดาษทั้งอาคาร", "Run a building-wide paper collection"),
  ["ตั้งกล่องเก็บกระดาษทุกชั้นแยกจากขยะทั่วไป",
   "จัดบริการทำลายเอกสารลับที่ส่งกระดาษต่อไปรีไซเคิล",
   "สื่อสารกับผู้เช่าเรื่องการลดการพิมพ์"],
  ["Put paper collection boxes on every floor",
   "Offer a secure-shredding service that recycles the paper",
   "Encourage tenants to print less"],
  rt, re_)
R('T-O01', 'opportunity', T, 'stream_paper', "paper_rank <= 3 and paper_pct >= 5", "45 + paper_pct",
  ("ลดการใช้กระดาษในสำนักงาน", "Cut paper use in the office"),
  ["ตั้งค่าเครื่องพิมพ์ให้พิมพ์ 2 หน้าและขาวดำเป็นค่าเริ่มต้น",
   "ใช้เอกสารดิจิทัลและลายเซ็นอิเล็กทรอนิกส์แทนการพิมพ์",
   "แยกกระดาษที่ใช้แล้วไว้ในกล่องเพื่อส่งรีไซเคิล"],
  ["Default printers to double-sided, black-and-white",
   "Use digital documents and e-signatures instead of printing",
   "Keep used paper in a box for recycling"],
  rt, re_)
R('E-O03', 'opportunity', E, 'stream_paper', "paper_rank <= 3 and paper_pct >= 5", "45 + paper_pct",
  ("ลดสื่อสิ่งพิมพ์ในกิจกรรม", "Cut printed material at events"),
  ["ใช้ QR code แทนแผ่นพับและเอกสารแจก",
   "พิมพ์เฉพาะที่จำเป็นและประเมินจำนวนให้พอดี",
   "เก็บป้ายและสื่อไว้ใช้ซ้ำในครั้งถัดไป"],
  ["Use QR codes instead of leaflets and handouts",
   "Print only what's needed, in the right quantity",
   "Keep signs and materials for reuse next time"],
  rt, re_)

rt, re_ = top_stream_reason("พลาสติก", "Plastic", "plastic_kg", "plastic_pct", "plastic_rank")
R('L-O04', 'opportunity', L, 'stream_plastic', "plastic_rank <= 3 and plastic_pct >= 5", "45 + plastic_pct",
  ("ลดพลาสติกใช้ครั้งเดียวในอาคาร", "Cut single-use plastic in the building"),
  ["ติดตั้งจุดเติมน้ำดื่มในพื้นที่ส่วนกลาง",
   "ขอความร่วมมือร้านค้าในอาคารลดถุงและภาชนะพลาสติก",
   "แยกขวด PET ใสเพื่อขายได้ราคาดีกว่า"],
  ["Install water refill stations in shared areas",
   "Ask shops in the building to cut bags and plastic containers",
   "Keep clear PET bottles apart; they sell for more"],
  rt, re_)
R('T-O03', 'opportunity', T, 'stream_plastic', "plastic_rank <= 3 and plastic_pct >= 5", "45 + plastic_pct",
  ("ลดพลาสติกใช้ครั้งเดียวในสำนักงาน", "Cut single-use plastic in the office"),
  ["ชวนพนักงานใช้แก้วและขวดน้ำส่วนตัว",
   "งดรับช้อนส้อมและถุงพลาสติกเมื่อสั่งอาหาร",
   "แยกขวดพลาสติกไว้ในถังรีไซเคิล"],
  ["Encourage staff to use their own cups and bottles",
   "Decline plastic cutlery and bags on food orders",
   "Keep plastic bottles in the recycling bin"],
  rt, re_)
R('E-O02', 'opportunity', E, 'stream_plastic', "plastic_rank <= 3 and plastic_pct >= 5", "45 + plastic_pct",
  ("ลดพลาสติกใช้ครั้งเดียวในกิจกรรม", "Cut single-use plastic at events"),
  ["ใช้แก้วหรือภาชนะใช้ซ้ำพร้อมระบบมัดจำ",
   "ตั้งจุดเติมน้ำดื่มแทนการแจกขวดน้ำ",
   "กำหนดให้ร้านค้างดถุงและหลอดพลาสติก"],
  ["Use reusable cups or containers with a deposit",
   "Set up water refill points instead of handing out bottles",
   "Ask vendors to drop plastic bags and straws"],
  rt, re_)

GM_REASON = ("แก้วและโลหะรวมกัน {glass_metal_kg:kg} ({glass_metal_pct:pct}) และอยู่ใน 3 อันดับแรกของขยะ วัสดุกลุ่มนี้รีไซเคิลได้เกือบทั้งหมดหากแยกออกมา",
             "Glass and metal together are {glass_metal_kg:kg} ({glass_metal_pct:pct}) and rank in the top 3; almost all of it is recyclable once separated.")
GM_WHEN = "(glass_rank <= 3 or metal_rank <= 3) and glass_metal_pct >= 5"
R('L-O05', 'opportunity', L, 'stream_glass_metal', GM_WHEN, "40 + glass_metal_pct",
  ("แยกขวดแก้วและกระป๋องจากศูนย์อาหาร/ร้านค้า", "Separate bottles and cans from food outlets"),
  ["ตั้งถังรับขวดแก้วและกระป๋องแยกในศูนย์อาหารและพื้นที่ร้านค้า",
   "กระป๋องอะลูมิเนียมมีราคารับซื้อสูง ควรแยกเก็บต่างหาก",
   "ให้ร้านค้าเทของเหลวออกก่อนทิ้ง"],
  ["Add separate bottle and can bins in food courts and retail areas",
   "Aluminium cans fetch a good price; keep them apart",
   "Ask outlets to pour out liquids first"],
  GM_REASON[0], GM_REASON[1])
R('T-O04', 'opportunity', T, 'stream_glass_metal', GM_WHEN, "40 + glass_metal_pct",
  ("แยกขวดและกระป๋องในแพนทรี่", "Separate bottles and cans in the pantry"),
  ["ตั้งถังรับขวดและกระป๋องแยกในแพนทรี่",
   "เทของเหลวออกก่อนทิ้งเพื่อลดการปนเปื้อน",
   "ส่งรวมกับระบบรีไซเคิลของอาคาร"],
  ["Add a bottle and can bin in the pantry",
   "Pour out liquids first to avoid contamination",
   "Hand them into the building's recycling"],
  GM_REASON[0], GM_REASON[1])
R('E-O04', 'opportunity', E, 'stream_glass_metal', GM_WHEN, "40 + glass_metal_pct",
  ("แยกขวดและกระป๋องจากจุดเครื่องดื่ม", "Separate bottles and cans at drink points"),
  ["วางถังขวดและกระป๋องไว้ติดกับจุดขายเครื่องดื่ม",
   "มอบหมายทีมงานเก็บรวบรวมหลังจบงาน",
   "ขายหรือบริจาคให้ผู้รับซื้อ"],
  ["Put bottle and can bins right next to drink stands",
   "Assign crew to collect them after the event",
   "Sell or donate them to a buyer"],
  GM_REASON[0], GM_REASON[1])

R('L-O06', 'opportunity', L, 'construction', "construction_kg >= 50 and construction_pct >= 5", "42 + construction_pct * 0.5",
  ("แยกจัดการขยะก่อสร้างและรีโนเวท", "Handle construction and renovation waste separately"),
  ["จัดพื้นที่คัดแยกวัสดุก่อสร้างโดยเฉพาะ",
   "ร่วมมือกับผู้รับซื้อวัสดุก่อสร้างรีไซเคิล เช่น เศษเหล็ก ไม้ คอนกรีต",
   "ระบุเงื่อนไขการคัดแยกไว้ในสัญญาผู้รับเหมา"],
  ["Set aside a sorting area for construction materials",
   "Partner with buyers of scrap metal, wood and concrete",
   "Write sorting requirements into contractor agreements"],
  "มีขยะก่อสร้าง {construction_kg:kg} ({construction_pct:pct} ของขยะทั้งหมด) ซึ่งเป็นปริมาณมากพอที่จะคุ้มกับการแยกจัดการและขายวัสดุบางส่วนได้",
  "{construction_kg:kg} of construction waste ({construction_pct:pct} of the total) is enough to justify separate handling and selling part of it.")

R('L-O07', 'opportunity', L, 'rdf', "total_kg >= 50 and general_pct >= 40 and wte_kg == 0", "38",
  ("ส่งขยะทั่วไปที่เผาได้ไปเป็นเชื้อเพลิง (RDF)", "Send combustible general waste to RDF"),
  ["ตรวจสอบกับผู้รับขยะว่ามีบริการแยกทำ RDF หรือไม่",
   "ช่วยลดปริมาณที่ส่งฝังกลบและค่าฝังกลบ",
   "แยกขยะเปียกออกก่อนเพื่อให้ขยะเผาได้มีคุณภาพ"],
  ["Ask your contractor whether they offer RDF processing",
   "It cuts the volume and cost of landfill",
   "Take out wet waste first so the fuel fraction stays usable"],
  "ขยะทั่วไป {general_kg:kg} ({general_pct:pct}) ทั้งหมดยังไม่มีส่วนที่ส่งไปทำเชื้อเพลิง การแยกส่วนที่เผาได้ออกไปจะลดการฝังกลบได้ทันที",
  "None of the {general_kg:kg} of general waste ({general_pct:pct}) goes to fuel yet; diverting the combustible part cuts landfill straight away.")

R('L-O08', 'opportunity', L, 'value', "recyclable_kg >= 20 and recyclable_pct >= 15", "35 + recyclable_pct * 0.5",
  ("ขายวัสดุรีไซเคิลแบบแยกชนิด", "Sell recyclables sorted by type"),
  ["แยกเก็บตามชนิด เช่น กระดาษขาวดำ กระดาษลัง PET กระป๋อง",
   "ทำสัญญากับผู้รับซื้อที่ให้ราคาตามชนิดวัสดุ",
   "ติดตามรายได้จากวัสดุรีไซเคิลเป็นรายเดือน"],
  ["Keep materials apart by type: white paper, cardboard, PET, cans",
   "Contract a buyer that prices by material type",
   "Track recycling revenue every month"],
  "มีวัสดุรีไซเคิล {recyclable_kg:kg} ({recyclable_pct:pct} ของขยะทั้งหมด) ในช่วงนี้ ซึ่งมากพอที่การแยกชนิดจะได้ราคาดีกว่าการขายรวม",
  "{recyclable_kg:kg} of recyclables ({recyclable_pct:pct} of the total) is enough volume for sorting by type to beat selling it mixed.")
R('T-O10', 'opportunity', T, 'value', "recyclable_kg >= 20 and recyclable_pct >= 15", "33 + recyclable_pct * 0.5",
  ("ส่งวัสดุรีไซเคิลเข้าโครงการของอาคาร", "Feed recyclables into the building's programme"),
  ["แยกกระดาษ ขวด และกระป๋องให้สะอาดและแห้ง",
   "สอบถามฝ่ายอาคารเรื่องจุดรวมและรอบรับวัสดุรีไซเคิล",
   "ขอข้อมูลปริมาณรีไซเคิลของผู้เช่าไว้ใช้ในรายงานองค์กร"],
  ["Keep paper, bottles and cans clean and dry",
   "Ask building management about collection points and pick-ups",
   "Request your recycling figures for your company reporting"],
  "ผู้เช่ามีวัสดุรีไซเคิล {recyclable_kg:kg} ({recyclable_pct:pct}) ซึ่งมากพอที่จะแยกส่งเข้าระบบรีไซเคิลของอาคารได้อย่างเป็นระบบ",
  "You have {recyclable_kg:kg} of recyclables ({recyclable_pct:pct}), enough to feed the building's recycling routinely.")
R('E-O05', 'opportunity', E, 'value', "recyclable_kg >= 20 and recyclable_pct >= 15", "35 + recyclable_pct * 0.5",
  ("รวบรวมวัสดุรีไซเคิลหลังจบกิจกรรม", "Collect recyclables after events"),
  ["แยกกระดาษลัง ขวด และกระป๋องไว้คนละจุด",
   "นัดผู้รับซื้อหรือผู้รับบริจาคมารับหลังจบงาน",
   "บันทึกปริมาณไว้เทียบในครั้งถัดไป"],
  ["Keep cardboard, bottles and cans at separate points",
   "Book a buyer or donation pick-up right after the event",
   "Record the amounts to compare next time"],
  "มีวัสดุรีไซเคิล {recyclable_kg:kg} ({recyclable_pct:pct}) จากกิจกรรม/พื้นที่เหล่านี้ ซึ่งคุ้มค่าที่จะรวบรวมส่งต่อแทนการทิ้งรวม",
  "These events/areas produced {recyclable_kg:kg} of recyclables ({recyclable_pct:pct}), worth collecting instead of binning.")

R('T-O05', 'opportunity', T, 'stream_general', "general_rank == 1 and general_pct >= 40 and total_kg >= 10", "40 + (general_pct - 40) * 0.8",
  ("คัดแยกขยะที่โต๊ะทำงาน", "Sort waste at the desk"),
  ["เปลี่ยนถังรวมเป็นถังแยก 2–3 ช่องตามโซนทำงาน",
   "กล่องและขวดที่ล้างแล้วรีไซเคิลได้ ไม่ต้องทิ้งเป็นขยะทั่วไป",
   "ตั้งเป้าลดสัดส่วนขยะทั่วไปลง 5–10% ในไตรมาสถัดไป"],
  ["Swap single bins for 2–3 compartment bins in each work zone",
   "Rinsed boxes and bottles are recyclable, not general waste",
   "Aim to cut the general-waste share by 5–10% next quarter"],
  "ขยะทั่วไปเป็นหมวดที่ใหญ่ที่สุดของผู้เช่า ({general_kg:kg} หรือ {general_pct:pct}) และการคัดแยกที่ต้นทางเป็นสิ่งที่ผู้เช่าควบคุมได้เองโดยตรง",
  "General waste is your largest stream ({general_kg:kg}, {general_pct:pct}), and sorting at source is fully in your hands.")
R('L-O11', 'opportunity', L, 'engage', "total_kg >= 50 and general_pct >= 40", "34",
  ("จัดแคมเปญคัดแยกร่วมกับผู้ใช้อาคาร", "Run a sorting campaign with occupants"),
  ["สื่อสารวิธีคัดแยกกับผู้เช่าและพนักงานผ่านป้ายและอีเมล",
   "แจ้งผลการคัดแยกรายเดือนให้ผู้เช่าทราบ",
   "มอบรางวัลให้ชั้นหรือผู้เช่าที่คัดแยกได้ดี"],
  ["Explain sorting to tenants and staff via signs and email",
   "Share monthly sorting results with tenants",
   "Reward the floors or tenants that sort best"],
  "ขยะทั่วไปคิดเป็น {general_pct:pct} ของ {total_kg:kg} ซึ่งส่วนใหญ่เกิดจากพฤติกรรมของผู้ใช้อาคาร การสื่อสารและแรงจูงใจจึงเป็นเครื่องมือที่เจ้าของอาคารใช้ได้ทันที",
  "General waste is {general_pct:pct} of {total_kg:kg}, largely down to occupant habits, so communication and incentives are levers the owner can use now.")
R('T-O08', 'opportunity', T, 'procurement', "total_kg >= 50 and general_pct >= 40", "30",
  ("ลดขยะตั้งแต่การจัดซื้อของสำนักงาน", "Cut waste at office procurement"),
  ["เลือกผู้ขายที่ใช้บรรจุภัณฑ์น้อยหรือรับคืนบรรจุภัณฑ์",
   "ซื้อของใช้สิ้นเปลืองแบบเติม (refill)",
   "งดของแจกหรือของที่ระลึกที่กลายเป็นขยะทันที"],
  ["Prefer suppliers with minimal or take-back packaging",
   "Buy refills for consumables",
   "Skip giveaways that become waste immediately"],
  "ขยะทั่วไปคิดเป็น {general_pct:pct} ของ {total_kg:kg} ส่วนหนึ่งมาจากบรรจุภัณฑ์และของใช้ครั้งเดียว ซึ่งผู้เช่าลดได้ตั้งแต่ขั้นตอนจัดซื้อ",
  "General waste is {general_pct:pct} of {total_kg:kg}; part of it is packaging and single-use items you can avoid at purchase.")
R('E-O06', 'opportunity', E, 'focus', "group_count >= 2 and top_group_share >= 40", "44 + (top_group_share - 40) * 0.4",
  ("เริ่มปรับปรุงที่ {top_group_label} ก่อน", "Start with {top_group_label}"),
  ["ทบทวนการจัดการขยะของ {top_group_label} เป็นลำดับแรก",
   "นำวิธีที่ได้ผลไปใช้กับกิจกรรม/พื้นที่อื่น",
   "ติดตามผลเทียบกับครั้งก่อน"],
  ["Review waste handling at {top_group_label} first",
   "Roll out what works to the other events/areas",
   "Track the result against last time"],
  "{top_group_label} มีขยะ {top_group_kg:kg} หรือ {top_group_share:pct} ของทั้งหมด การปรับปรุงที่จุดนี้จึงให้ผลมากกว่าการกระจายไปทุกจุดพร้อมกัน",
  "{top_group_label} produced {top_group_kg:kg}, {top_group_share:pct} of the total, so improving it beats spreading effort everywhere at once.")

GOOD_WHEN = "has_prev and prev_kg >= 5 and change_pct <= -10 and change_pct > -60"
GOOD_REASON = ("ขยะรวม {cur_kg:kg} เทียบกับ {prev_kg:kg} ในช่วง {prev_label} ลดลง {change_pct_abs:pct} เป็นการลดลงที่ชัดเจนแต่ไม่มากผิดปกติ จึงน่าจะมาจากการเปลี่ยนแปลงจริง",
               "{cur_kg:kg} against {prev_kg:kg} for {prev_label}, down {change_pct_abs:pct}: a clear but not suspicious drop, likely a real change.")
for rid, modes, title, bth, ben in [
    ('L-O09', L, ("ต่อยอดแนวโน้มการลดขยะ", "Build on the drop in waste"),
     ["แจ้งผลการลดขยะ {change_pct_abs:pct} ให้ผู้ใช้อาคารรับทราบ", "บันทึกว่ามาตรการใดได้ผล เพื่อขยายไปพื้นที่อื่น", "ตั้งเป้าหมายรายเดือนเพื่อรักษาระดับนี้"],
     ["Share the {change_pct_abs:pct} reduction with occupants", "Note what worked and roll it out to other areas", "Set a monthly target to hold the gain"]),
    ('T-O06', T, ("ต่อยอดแนวโน้มการลดขยะ", "Build on the drop in waste"),
     ["แจ้งผลการลดขยะ {change_pct_abs:pct} ให้ทีมรับทราบ", "ตั้งเป้าหมายรายเดือนเพื่อรักษาระดับนี้", "แบ่งปันวิธีที่ได้ผลกับทีมอื่นในองค์กร"],
     ["Share the {change_pct_abs:pct} reduction with the team", "Set a monthly target to hold the gain", "Pass on what worked to other teams"]),
    ('E-O07', E, ("ต่อยอดแนวโน้มการลดขยะ", "Build on the drop in waste"),
     ["สรุปสิ่งที่ทำต่างจากครั้งก่อนไว้เป็นแนวทาง", "ใช้แนวทางเดียวกันกับกิจกรรมครั้งถัดไป", "สื่อสารผลลัพธ์กับผู้จัดและผู้เข้าร่วม"],
     ["Write down what you did differently", "Use the same approach at the next event", "Share the result with organisers and attendees"]),
]:
    R(rid, 'opportunity', modes, 'trend_good', GOOD_WHEN, "38 + min(change_pct_abs, 50) * 0.3", title, bth, ben, GOOD_REASON[0], GOOD_REASON[1])

R('L-O10', 'opportunity', LT, 'trend_good', "has_prev and prev_kg >= 5 and total_kg >= 5 and diversion_change_pts >= 5",
  "36 + min(diversion_change_pts, 30) * 0.5",
  ("การคัดแยกดีขึ้น ต่อยอดได้", "Sorting is improving"),
  ["สัดส่วนขยะที่คัดแยกได้เพิ่มจาก {diversion_pct_prev:pct} เป็น {diversion_pct:pct}",
   "ใช้ผลนี้สื่อสารและชวนพื้นที่อื่นทำตาม",
   "ตั้งเป้าหมายอัตราการคัดแยกรายเดือน"],
  ["The sorted share rose from {diversion_pct_prev:pct} to {diversion_pct:pct}",
   "Use it to bring other areas on board",
   "Set a monthly sorting-rate target"],
  "สัดส่วนขยะรีไซเคิลและขยะอินทรีย์เพิ่มจาก {diversion_pct_prev:pct} ในช่วง {prev_label} เป็น {diversion_pct:pct} ({diversion_change_pts:pts}) เป็นสัญญาณว่าการคัดแยกได้ผล",
  "The recyclable + organic share rose from {diversion_pct_prev:pct} ({prev_label}) to {diversion_pct:pct} ({diversion_change_pts:pts}), a sign sorting is working.")

ZW_REASON = ("สัดส่วนขยะที่คัดแยกได้ (รีไซเคิลและอินทรีย์) อยู่ที่ {diversion_pct:pct} ซึ่งสูงกว่าครึ่งหนึ่งอย่างชัดเจน จึงพร้อมตั้งเป้าหมายที่สูงขึ้น",
             "The sorted share (recyclable + organic) is {diversion_pct:pct}, well above half, so a higher target is realistic.")
R('L-O12', 'opportunity', ['location', 'tenant', 'tag'], 'zero_waste', "total_kg >= 10 and diversion_pct >= 60", "35 + (diversion_pct - 60) * 0.5",
  ("ก้าวสู่เป้าหมาย Zero Waste", "Move toward Zero Waste"),
  ["ตั้งเป้าอัตราการคัดแยก 80–90% ตามแนวทาง Zero Waste",
   "มุ่งลดขยะทั่วไปที่เหลือ เช่น บรรจุภัณฑ์ปนเปื้อน",
   "สื่อสารความสำเร็จในรายงานความยั่งยืน"],
  ["Target an 80–90% sorting rate, in line with Zero Waste practice",
   "Go after the remaining general waste, e.g. contaminated packaging",
   "Report the result in sustainability reporting"],
  ZW_REASON[0], ZW_REASON[1])

# ============================== quick wins ==============================
SIGN_TH = ["ตรวจสอบและเปลี่ยนป้ายคัดแยกที่ซีดจาง", "เพิ่มรูปภาพตัวอย่างบนป้าย ไม่ใช่แค่ข้อความ", "ใช้สีที่สอดคล้องกันทุกจุด"]
SIGN_EN = ["Audit and replace faded segregation signs", "Add visual examples on signs, not just text", "Use consistent colour coding at all stations"]
SIGN_GEN_REASON = ("ขยะทั่วไปคิดเป็น {general_pct:pct} ของขยะทั้งหมด ซึ่งมากกว่าครึ่ง ป้ายที่ชัดเจนช่วยให้ทิ้งถูกถังได้ทันทีโดยแทบไม่มีค่าใช้จ่าย",
                   "General waste is {general_pct:pct} of the total, more than half; clear signs get waste into the right bin straight away at almost no cost.")
SIGN_UNSPEC_REASON = ("ขยะที่บันทึกเป็นประเภทรวมหรือไม่ระบุมี {unspecified_kg:kg} ({unspecified_pct:pct} ของขยะทั้งหมด) แสดงว่าจุดทิ้งยังแยกได้ไม่ละเอียด",
                      "{unspecified_kg:kg} ({unspecified_pct:pct} of the total) was recorded as mixed or unspecified, so bins aren't being sorted finely.")
for rid, modes, title in [
    ('L-Q01', L, ("ปรับปรุงป้ายบอกทางอย่างง่าย", "Simple signage fix")),
    ('T-Q01', T, ("ติดป้ายคัดแยกที่ถังในสำนักงาน", "Put sorting signs on office bins")),
    ('E-Q01', E, ("ป้ายคัดแยกแบบมีรูปภาพที่จุดทิ้ง", "Picture signs at every bin station")),
]:
    R(rid, 'quickwin', modes, 'signage', "total_kg >= 5 and general_pct >= 50", "50 + (general_pct - 50) * 0.5", title, SIGN_TH, SIGN_EN, *SIGN_GEN_REASON)
R('L-Q02', 'quickwin', ['location', 'tenant', 'tag'], 'signage', "total_kg >= 5 and unspecified_pct >= 15", "48 + min(unspecified_pct, 50) * 0.3",
  ("ปรับปรุงป้ายบอกทางอย่างง่าย", "Simple signage fix"), SIGN_TH, SIGN_EN, *SIGN_UNSPEC_REASON)

BIN_WHEN = "total_kg >= 5 and general_pct >= 40 and general_kg > diversion_kg"
BIN_REASON = ("ขยะทั่วไป {general_kg:kg} มากกว่าขยะที่คัดแยกได้ {diversion_kg:kg} การมีถังรีไซเคิลอยู่ข้างถังขยะทั่วไปทุกจุดทำให้การแยกเป็นเรื่องง่ายที่สุด",
              "General waste ({general_kg:kg}) outweighs sorted waste ({diversion_kg:kg}); a recycling bin beside every general bin makes sorting the easy choice.")
R('L-Q03', 'quickwin', L, 'bins', BIN_WHEN, "46 + (general_pct - 40) * 0.4",
  ("การเพิ่มประสิทธิภาพตำแหน่งถังขยะ", "Bin placement optimisation"),
  ["วางถังรีไซเคิลคู่กับถังขยะทั่วไป", "เพิ่มถังในจุดที่เกิดขยะมาก (ห้องพัก ห้องถ่ายเอกสาร)", "เอาถังขยะทั่วไปออกจากจุดที่ควรรีไซเคิล"],
  ["Place recycling bins next to general waste bins", "Add bins in high-waste areas (break rooms, copy areas)", "Remove general waste bins from recyclable zones"],
  *BIN_REASON)
R('T-Q03', 'quickwin', T, 'bins', BIN_WHEN, "46 + (general_pct - 40) * 0.4",
  ("วางถังรีไซเคิลคู่ถังขยะทั่วไปในสำนักงาน", "Pair recycling and general bins in the office"),
  ["วางถังรีไซเคิลไว้ข้างถังขยะทั่วไปทุกจุด", "หากถังไม่พอ ติดต่อฝ่ายอาคารเพื่อขอถังเพิ่ม", "ย้ายถังไปไว้ใกล้แพนทรี่และห้องถ่ายเอกสาร"],
  ["Put a recycling bin next to every general bin", "Ask building management for more bins if needed", "Move bins close to the pantry and copy room"],
  *BIN_REASON)
R('E-Q02', 'quickwin', E, 'bins', BIN_WHEN, "46 + (general_pct - 40) * 0.4",
  ("เจ้าหน้าที่ประจำจุดทิ้งขยะช่วงคนเยอะ", "Staff the bin stations at peak times"),
  ["ให้ทีมงานช่วยแนะนำการทิ้งที่จุดคัดแยกช่วงพีค", "วางจุดคัดแยกครบชุดทุกจุด ไม่มีถังเดี่ยว", "รวมจุดทิ้งให้น้อยลงแต่ครบถังทุกประเภท"],
  ["Have crew guide people at the stations during peaks", "Make every station a full set, never a lone bin", "Fewer stations, each with every bin type"],
  *BIN_REASON)

SPEC_REASON = ("มีวัสดุรีไซเคิลที่บันทึกเป็นประเภทรวมหรือไม่ระบุ {unspecified_recyclable_kg:kg} คิดเป็น {unspecified_recyclable_share:pct} ของวัสดุรีไซเคิลทั้งหมด การระบุชนิดช่วยให้คำนวณผลกระทบได้แม่นยำและขายได้ราคาดีกว่า",
               "{unspecified_recyclable_kg:kg} of recyclables ({unspecified_recyclable_share:pct} of all recyclables) was recorded as mixed/unspecified; recording the type makes the impact figures accurate and sells for more.")
R('L-Q04', 'quickwin', ['location', 'tenant', 'tag'], 'specify', "unspecified_recyclable_kg >= 1 and unspecified_recyclable_share >= 10",
  "47 + min(unspecified_recyclable_share, 60) * 0.3",
  ("ระบุชนิดวัสดุรีไซเคิลตอนบันทึก", "Record recyclables by type"),
  ["เลือกชนิดย่อย เช่น กระดาษขาวดำ PET กระป๋อง แทน \"วัสดุรีไซเคิลรวม\"", "ช่วยให้คำนวณการลดก๊าซเรือนกระจกได้แม่นยำขึ้น", "วัสดุที่แยกชนิดขายได้ราคาดีกว่าวัสดุรวม"],
  ["Pick the specific type (white paper, PET, cans) instead of \"mixed recyclables\"", "Makes the greenhouse-gas calculation more accurate", "Sorted materials sell for more than mixed ones"],
  *SPEC_REASON)

R('L-Q05', 'quickwin', L, 'cardboard', "cardboard_kg >= 3", "38",
  ("จัดจุดพับและมัดกล่องกระดาษลัง", "Set up a cardboard flattening point"),
  ["พับกล่องให้แบนและมัดรวมก่อนส่ง ลดพื้นที่จัดเก็บ", "เก็บให้แห้ง ไม่ปนเทปและพลาสติก", "นัดรอบรับซื้อประจำกับผู้รับซื้อ"],
  ["Flatten and bundle boxes to save storage space", "Keep them dry and free of tape and plastic", "Agree a regular pick-up with a buyer"],
  "มีกระดาษลัง {cardboard_kg:kg} ในช่วงนี้ ซึ่งเป็นวัสดุที่ขายได้ทันทีหากพับเก็บให้แห้งและสะอาด",
  "{cardboard_kg:kg} of cardboard this period, which sells straight away if kept flat, dry and clean.")

MIXED_REASON = ("กระดาษรวม (จับจั๊ว) {mixed_paper_kg:kg} คิดเป็น {mixed_paper_share:pct} ของกระดาษทั้งหมด กระดาษขาวดำที่ปนอยู่จะขายได้ราคาต่ำลงตามกระดาษรวม",
                "Mixed paper is {mixed_paper_kg:kg}, {mixed_paper_share:pct} of all paper; white paper mixed into it sells at the lower mixed-paper price.")
R('L-Q06', 'quickwin', LT, 'paper_sort', "mixed_paper_kg >= 2 and mixed_paper_share >= 30", "44",
  ("แยกกระดาษขาวดำออกจากกระดาษรวม", "Pull white paper out of mixed paper"),
  ["ตั้งกล่องเก็บกระดาษ A4 ขาวดำไว้ข้างเครื่องพิมพ์", "กระดาษขาวดำขายได้ราคาสูงกว่ากระดาษรวมมาก", "เอกสารลับให้ย่อยเส้นแล้วแยกเก็บเป็นกระดาษย่อย"],
  ["Put a box for white A4 paper next to each printer", "White office paper sells for much more than mixed paper", "Shred confidential papers and keep the shreds separate"],
  *MIXED_REASON)

R('T-Q02', 'quickwin', T, 'paper_qw', "paper_pct >= 10 and paper_kg >= 3", "40 + paper_pct * 0.5",
  ("ตั้งค่าพิมพ์สองหน้าเป็นค่าเริ่มต้น", "Make double-sided printing the default"),
  ["ตั้งค่าเริ่มต้นของเครื่องพิมพ์ทุกเครื่องเป็นพิมพ์สองหน้า", "ให้ยืนยันก่อนพิมพ์เอกสารที่ยาวเกิน 20 หน้า", "ติดป้ายเตือนใกล้เครื่องพิมพ์"],
  ["Set every printer to double-sided by default", "Require confirmation for jobs over 20 pages", "Put a reminder sign next to the printers"],
  "กระดาษคิดเป็น {paper_pct:pct} ของขยะ ({paper_kg:kg}) การพิมพ์สองหน้าลดกระดาษได้ทันทีโดยไม่ต้องลงทุน",
  "Paper is {paper_pct:pct} of all waste ({paper_kg:kg}); double-sided printing cuts it immediately at no cost.")
R('T-Q04', 'quickwin', T, 'bins', "total_kg >= 20 and general_pct >= 55", "36",
  ("ยกเลิกถังขยะประจำโต๊ะ", "Replace personal desk bins"),
  ["ใช้จุดทิ้งรวมแบบแยกประเภทแทนถังใต้โต๊ะ", "ทุกครั้งที่เดินไปทิ้งจะเห็นป้ายคัดแยก", "ลดงานเก็บขยะรายวันของแม่บ้าน"],
  ["Use shared sorting stations instead of under-desk bins", "Every trip to the bin passes a sorting sign", "Less daily bin-emptying for cleaners"],
  "ขยะทั่วไปคิดเป็น {general_pct:pct} ของขยะทั้งหมด ถังใต้โต๊ะมักทำให้ทุกอย่างกลายเป็นขยะทั่วไป",
  "General waste is {general_pct:pct} of the total; under-desk bins tend to turn everything into general waste.")

RINSE_WHEN = "organic_kg >= 5 and plastic_kg >= 2"
RINSE_REASON = ("พบทั้งเศษอาหาร {organic_kg:kg} และพลาสติก {plastic_kg:kg} ซึ่งมักปนเปื้อนกันเมื่อทิ้งพร้อมกัน ทำให้พลาสติกรีไซเคิลไม่ได้",
                "Both food waste ({organic_kg:kg}) and plastic ({plastic_kg:kg}) are present, and they contaminate each other when binned together.")
R('T-Q05', 'quickwin', T, 'rinse', RINSE_WHEN, "34",
  ("เทเศษอาหารและล้างบรรจุภัณฑ์ก่อนทิ้ง", "Empty and rinse packaging before binning"),
  ["ตั้งจุดเทน้ำและเศษอาหารในแพนทรี่", "บรรจุภัณฑ์ที่สะอาดรีไซเคิลได้และไม่ทำให้วัสดุอื่นปนเปื้อน", "ติดป้ายเตือนบนถังรีไซเคิล"],
  ["Add a place in the pantry to empty liquids and food", "Clean packaging recycles and doesn't spoil other materials", "Put a reminder on the recycling bins"],
  *RINSE_REASON)
R('E-Q05', 'quickwin', E, 'rinse', RINSE_WHEN, "34",
  ("จุดเทน้ำและเศษอาหารก่อนถึงถังรีไซเคิล", "An emptying point before the recycling bins"),
  ["วางถังเทน้ำ/น้ำแข็งไว้หน้าจุดคัดแยก", "ให้ทีมงานช่วยแนะนำช่วงคนเยอะ", "แยกภาชนะที่สะอาดออกจากที่เปื้อน"],
  ["Put a liquid/ice tip bin in front of each station", "Have crew help at busy times", "Keep clean containers apart from dirty ones"],
  *RINSE_REASON)
R('E-Q04', 'quickwin', E, 'vendor', "organic_pct >= 5 or plastic_pct >= 5", "37",
  ("แจ้งร้านค้าและผู้จัดเรื่องการคัดแยกล่วงหน้า", "Brief vendors and organisers in advance"),
  ["กำหนดชนิดบรรจุภัณฑ์ที่ร้านค้าใช้ได้ล่วงหน้า", "แจ้งจุดทิ้งและวิธีแยกให้ร้านค้าทราบก่อนวันงาน", "ให้ร้านค้าแยกเศษอาหารของตัวเองก่อนส่งทิ้ง"],
  ["Agree allowed packaging with vendors in advance", "Tell vendors where and how to sort before the day", "Have vendors separate their own food scraps"],
  "ขยะจากกิจกรรม/พื้นที่เหล่านี้มีเศษอาหาร {organic_pct:pct} และพลาสติก {plastic_pct:pct} ซึ่งส่วนใหญ่มาจากร้านค้า การตกลงก่อนวันงานจึงลดได้ตั้งแต่ต้นทาง",
  "Food waste is {organic_pct:pct} and plastic {plastic_pct:pct} of the waste here, mostly from vendors, so agreeing things before the day cuts it at source.")

R('L-Q07', 'quickwin', ['location', 'tenant', 'tag'], 'ewaste', "electronic_kg > 0", "42",
  ("จัดจุดรับขยะอิเล็กทรอนิกส์", "Set up an e-waste drop point"),
  ["ตั้งกล่องรับสายชาร์จและอุปกรณ์ขนาดเล็กที่เสีย", "ส่งต่อผู้รีไซเคิลขยะอิเล็กทรอนิกส์ที่ได้รับอนุญาต", "ห้ามทิ้งปนกับขยะทั่วไป"],
  ["Put out a box for dead chargers and small devices", "Pass them to a licensed e-waste recycler", "Never put them in general waste"],
  "พบขยะอิเล็กทรอนิกส์ {electronic_kg:kg} ในช่วงนี้ ซึ่งมีสารอันตรายและต้องแยกจัดการเฉพาะ",
  "{electronic_kg:kg} of e-waste this period, which contains hazardous parts and needs separate handling.")
R('L-Q08', 'quickwin', ['location', 'tenant', 'tag'], 'hazard_qw', "hazardous_kg > 0", "58 + min(hazardous_pct, 20)",
  ("จัดจุดรวมถ่านไฟฉายและหลอดไฟ", "Set up a battery and lamp collection point"),
  ["ตั้งกล่องรวบรวมที่มีฝาปิดและป้ายชัดเจน", "แจ้งทุกคนว่าห้ามทิ้งลงถังขยะทั่วไป", "นัดส่งกำจัดเป็นรอบ"],
  ["Put out a lidded, clearly labelled collection box", "Tell everyone these never go in the general bin", "Schedule regular hand-overs for disposal"],
  "พบขยะอันตราย {hazardous_kg:kg} การมีจุดรวมเฉพาะช่วยป้องกันไม่ให้ปนกับขยะอื่นตั้งแต่ต้นทาง",
  "{hazardous_kg:kg} of hazardous waste was recorded; a dedicated drop point keeps it out of other streams from the start.")

BRIEF_WHEN = "has_prev and prev_kg >= 5 and diversion_change_pts <= -5"
BRIEF_REASON = ("สัดส่วนการคัดแยกลดลง {diversion_change_pts:pts} จาก{compare_word} การทบทวนสั้น ๆ มักได้ผลเร็วกว่าการเปลี่ยนอุปกรณ์",
                "The sorted share fell {diversion_change_pts:pts} on {compare_word}; a short refresher usually works faster than new equipment.")
R('L-Q09', 'quickwin', L, 'briefing', BRIEF_WHEN, "43",
  ("อบรมแม่บ้านเรื่องการคัดแยก", "Refresh housekeeping on sorting"),
  ["ทบทวนการเก็บขยะแยกประเภทกับแม่บ้านทุกกะ", "ห้ามเทถังรีไซเคิลรวมกับถังขยะทั่วไป", "ติดตามผลภายในเดือนถัดไป"],
  ["Run a sorting refresher with every housekeeping shift", "Never empty recycling bins into general waste", "Check the result next month"],
  *BRIEF_REASON)
R('T-Q07', 'quickwin', T, 'briefing', BRIEF_WHEN, "43",
  ("ย้ำวิธีคัดแยกกับพนักงาน", "Refresh sorting know-how with staff"),
  ["สรุปวิธีคัดแยก 1 หน้าส่งในกลุ่มแชทของทีม", "ใช้เวลา 5 นาทีในการประชุมประจำสัปดาห์", "ชี้จุดที่ทิ้งผิดบ่อยพร้อมรูปตัวอย่าง"],
  ["Send a one-page sorting guide to the team chat", "Take 5 minutes of the weekly meeting", "Show photos of the most common mistakes"],
  *BRIEF_REASON)

R('L-Q10', 'quickwin', L, 'data_qw', "has_data and days_since_last_record >= 7 and days_since_last_record < 14", "40",
  ("ตั้งรอบชั่งและบันทึกขยะให้สม่ำเสมอ", "Weigh and record on a fixed schedule"),
  ["กำหนดวันและเวลาชั่งขยะประจำ", "มอบหมายผู้รับผิดชอบหลักและผู้แทน", "ตรวจรายการในระบบทุกสิ้นเดือน"],
  ["Fix weighing days and times", "Name an owner and a backup", "Review the records at every month end"],
  "ไม่มีการบันทึกขยะมา {days_since_last_record:int} วัน (บันทึกล่าสุด {last_record_date}) ซึ่งเริ่มนานกว่ารอบปกติ",
  "Nothing has been recorded for {days_since_last_record:int} days (last record {last_record_date}), longer than the usual cycle.")
R('T-Q09', 'quickwin', T, 'data_qw', "has_data and days_since_last_record >= 7 and days_since_last_record < 14", "40",
  ("ตรวจกับฝ่ายอาคารว่าขยะของผู้เช่าถูกชั่งครบ", "Check with the building that your waste is weighed"),
  ["สอบถามรอบการชั่งขยะของผู้เช่ากับฝ่ายอาคาร", "ตรวจว่าทีมนำขยะไปจุดชั่งตามที่กำหนด", "แจ้งหากพบว่าขยะบางส่วนไม่ได้ถูกชั่ง"],
  ["Ask building management about your weighing schedule", "Check your team uses the weighing point", "Report any waste that isn't being weighed"],
  "ไม่มีการบันทึกขยะของผู้เช่ามา {days_since_last_record:int} วัน (บันทึกล่าสุด {last_record_date}) ซึ่งเริ่มนานกว่ารอบปกติ",
  "Nothing has been recorded for you for {days_since_last_record:int} days (last record {last_record_date}), longer than the usual cycle.")

R('T-Q10', 'quickwin', T, 'assign', "unassigned_share >= 20 and group_count >= 1", "45 + min(unassigned_share, 60) * 0.2",
  ("ระบุผู้เช่าในทุกการชั่ง", "Tag the tenant on every weighing"),
  ["ตั้งค่า PIN หรือ QR แยกรายผู้เช่า", "ตรวจรายการที่ยังไม่ระบุผู้เช่าและแก้ไข", "แจ้งผู้ชั่งให้เลือกผู้เช่าทุกครั้ง"],
  ["Set up a PIN or QR code per tenant", "Review records without a tenant and fix them", "Remind whoever weighs to pick the tenant every time"],
  "ขยะ {unassigned_kg:kg} ({unassigned_share:pct} ของทั้งหมด) ยังไม่ได้ระบุผู้เช่า รายงานรายผู้เช่าจึงยังไม่ครบ",
  "{unassigned_kg:kg} ({unassigned_share:pct} of the total) has no tenant yet, so per-tenant reporting is incomplete.")
R('E-Q07', 'quickwin', E, 'assign', "unassigned_share >= 20 and group_count >= 1", "45 + min(unassigned_share, 60) * 0.2",
  ("ติดแท็กให้ครบทุกรายการ", "Tag every record"),
  ["เลือกแท็กกิจกรรม/พื้นที่ทุกครั้งที่บันทึก", "ตรวจรายการที่ยังไม่มีแท็กและแก้ไข", "ตั้งชื่อแท็กให้ชัดเจนและใช้ซ้ำได้"],
  ["Pick the event/area tag every time you record", "Review untagged records and fix them", "Give tags clear, reusable names"],
  "ขยะ {unassigned_kg:kg} ({unassigned_share:pct} ของทั้งหมด) ยังไม่มีแท็ก การเปรียบเทียบระหว่างกิจกรรม/พื้นที่จึงยังไม่ครบ",
  "{unassigned_kg:kg} ({unassigned_share:pct} of the total) is untagged, so comparisons between events/areas are incomplete.")
R('E-Q06', 'quickwin', E, 'hazard_qw', "hazardous_kg > 0", "58 + min(hazardous_pct, 20)",
  ("ภาชนะแยกขยะอันตรายในกิจกรรม", "A hazardous-waste container at events"),
  ["เตรียมภาชนะมีฝาปิดสำหรับถ่านและกระป๋องสเปรย์", "แจ้งทีมงานให้เก็บแยกตั้งแต่ติดตั้งงาน", "ส่งต่อผู้รับกำจัดที่ได้รับอนุญาต"],
  ["Provide a lidded container for batteries and aerosol cans", "Brief crew to keep them apart from set-up", "Hand them to a licensed contractor"],
  "พบขยะอันตราย {hazardous_kg:kg} จากกิจกรรม/พื้นที่เหล่านี้ ภาชนะเฉพาะช่วยไม่ให้ปนกับขยะอื่น",
  "{hazardous_kg:kg} of hazardous waste came from these events/areas; a dedicated container keeps it out of other streams.")

# E-Q07 above conflicts id-wise with nothing; L-Q08 (all modes) and E-Q06 share group — drop L-Q08 for tag
for r in RULES:
    if r['id'] == 'L-Q08':
        r['modes'] = ['location', 'tenant']

FALLBACK = {
    'no_data': {
        'title': {'th': "ยังไม่มีข้อมูลในช่วงเวลาที่เลือก", 'en': "No data for the selected period"},
        'bullets': {'th': ["เลือกช่วงเวลาหรือสถานที่ที่มีการบันทึกขยะ"], 'en': ["Pick a period or location that has waste records"]},
        'reason': {'th': "ไม่พบรายการขยะในช่วงเวลาและตัวกรองที่เลือก จึงยังวิเคราะห์ไม่ได้", 'en': "There are no waste records for this period and filter, so nothing can be analysed yet."},
    },
}
RISK_FB = {
    'title': {'th': "ยังไม่พบความเสี่ยงที่ต้องเฝ้าระวัง", 'en': "No risks flagged"},
    'bullets': {'th': ["ตัวชี้วัดในช่วงนี้อยู่ในระดับปกติ", "ติดตามแนวโน้มต่อเนื่องทุกเดือน"], 'en': ["Indicators for this period look normal", "Keep tracking the trend every month"]},
    'reason': {'th': "ไม่พบการเพิ่มขึ้นที่ชัดเจนจาก{compare_word} และสัดส่วนขยะทั่วไปยังไม่เกินครึ่งหนึ่ง{trend_note}", 'en': "No clear rise on {compare_word}, and general waste is not over half the total.{trend_note}"},
}
FALLBACK['location'] = {
    'risk': RISK_FB,
    'opportunity': {
        'title': {'th': "ตั้งเป้าหมายลดขยะของอาคาร", 'en': "Set a building reduction target"},
        'bullets': {'th': ["ใช้ยอดขยะช่วงนี้เป็นฐาน แล้วตั้งเป้าลด 5%", "ติดตามผลในรายงานทุกเดือน"], 'en': ["Use this period as the baseline and aim for 5% less", "Track progress in this report every month"]},
        'reason': {'th': "ยังไม่มีหมวดขยะใดโดดเด่นพอสำหรับคำแนะนำเฉพาะ การตั้งเป้าหมายจึงเป็นจุดเริ่มต้นที่ดี", 'en': "No stream stands out enough for specific advice yet, so a baseline target is the best starting point."},
    },
    'quickwin': {
        'title': {'th': "ปรับปรุงป้ายบอกทางอย่างง่าย", 'en': "Simple signage fix"},
        'bullets': {'th': SIGN_TH[:2], 'en': SIGN_EN[:2]},
        'reason': {'th': "เป็นคำแนะนำพื้นฐานที่ทำได้ทันทีโดยแทบไม่มีค่าใช้จ่าย", 'en': "A baseline fix you can do today at almost no cost."},
    },
}
FALLBACK['tenant'] = {
    'risk': RISK_FB,
    'opportunity': {
        'title': {'th': "ตั้งเป้าหมายลดขยะของทีม", 'en': "Set a team reduction target"},
        'bullets': {'th': ["ใช้ยอดขยะช่วงนี้เป็นฐาน แล้วตั้งเป้าลด 5%", "แจ้งผลให้ทีมทราบทุกเดือน"], 'en': ["Use this period as the baseline and aim for 5% less", "Share progress with the team every month"]},
        'reason': {'th': "ยังไม่มีหมวดขยะใดโดดเด่นพอสำหรับคำแนะนำเฉพาะ การตั้งเป้าหมายร่วมกันจึงเป็นจุดเริ่มต้นที่ดี", 'en': "No stream stands out enough for specific advice yet, so a shared target is the best starting point."},
    },
    'quickwin': {
        'title': {'th': "ติดป้ายคัดแยกที่ถังในสำนักงาน", 'en': "Put sorting signs on office bins"},
        'bullets': {'th': SIGN_TH[:2], 'en': SIGN_EN[:2]},
        'reason': {'th': "เป็นคำแนะนำพื้นฐานที่ผู้เช่าทำได้ทันทีโดยแทบไม่มีค่าใช้จ่าย", 'en': "A baseline fix you can do today at almost no cost."},
    },
}
FALLBACK['tag'] = {
    'risk': RISK_FB,
    'opportunity': {
        'title': {'th': "บันทึกผลไว้เทียบกับกิจกรรมครั้งถัดไป", 'en': "Record results to compare with the next event"},
        'bullets': {'th': ["ใช้ข้อมูลครั้งนี้เป็นฐานของกิจกรรมลักษณะเดียวกัน", "ตั้งเป้าลดขยะต่อผู้เข้าร่วมในครั้งถัดไป"], 'en': ["Use this as the baseline for similar events", "Set a per-attendee reduction target for next time"]},
        'reason': {'th': "ยังไม่มีหมวดขยะใดโดดเด่นพอสำหรับคำแนะนำเฉพาะ ข้อมูลครั้งนี้จึงมีค่าที่สุดในฐานะเกณฑ์เปรียบเทียบ", 'en': "No stream stands out enough for specific advice, so this data is most useful as a benchmark."},
    },
    'quickwin': {
        'title': {'th': "ป้ายคัดแยกแบบมีรูปภาพที่จุดทิ้ง", 'en': "Picture signs at every bin station"},
        'bullets': {'th': SIGN_TH[:2], 'en': SIGN_EN[:2]},
        'reason': {'th': "เป็นคำแนะนำพื้นฐานที่ทำได้ทันทีในทุกกิจกรรม", 'en': "A baseline fix that works at any event."},
    },
}

doc = {
    'version': 3,
    'description': "Rules for the Risks / Opportunities / Quick wins cards of the waste report (web Compare tab + PDF export), per report mode: location = building owner/operator, tenant = occupant, tag = event/tagged area. Evaluated by GEPPPlatform/services/cores/reports/report_insights.py over the scope's own data, current period vs the same period last year (or last month). See README.md for metrics and syntax.",
    'max_items_per_section': 2,
    'rules': RULES,
    'fallback': FALLBACK,
}
ids = [r['id'] for r in RULES]
assert len(ids) == len(set(ids)), [i for i in ids if ids.count(i) > 1]
json.dump(doc, open(sys.argv[1], 'w', encoding='utf-8'), ensure_ascii=False, indent=2)
from collections import Counter
print(len(RULES), Counter((m, r['section']) for r in RULES for m in r['modes']))
