from datetime import datetime
from pathlib import Path

from reportlab.pdfgen import canvas
from reportlab.lib.units import inch
from reportlab.lib import colors
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfbase.pdfmetrics import stringWidth
from reportlab.graphics.shapes import Drawing
from reportlab.graphics.charts.piecharts import Pie
from reportlab.graphics import renderPDF
MATERIAL_COLORS = {
    "Recyclable Waste": colors.HexColor("#fff8c8"),
    "Organic Waste": colors.HexColor("#b0dad6"),
    "Electronic Waste": colors.HexColor("#e8e5ef"),
    "Bio-Hazardous Waste": colors.HexColor("#e6b8af"),
    "Hazardous Waste": colors.HexColor("#f4cccc"),
    "Waste To Energy": colors.HexColor("#fce5cd"),
    "General Waste": colors.HexColor("#cfe2f3"),
    "Construction Waste": colors.HexColor("#e8e5ef"),
    "Electronic Waste": colors.HexColor("#d9d9d9"),
}
main_material_colorPalette = [
  "#180055",
  "#1a1662",
  "#1b296d",
  "#1c3b77",
  "#1d4c81",
  "#215d8b",
  "#2880a0",
  "#3091aa",
  "#44a2b1",
  "#58b4b9",
  "#6cc5c0",
  "#85d5ca",
  "#a7e3d7",
  "#c9f1e4",
  "#eafff1"
]
sub_material_colorPalette = [
    "#00313a",
    "#073f3e",
    "#0e4d41",
    "#155b45",
    "#1e6a48",
    "#1e6a48",
    "#3b9752",
    "#4ca658",
    "#62b55e",
    "#79c365",
    "#8fd16c",
    "#a6df73",
    "#c5ea99",
    "#e2f5bd",
    "#ffffe0"
  ]
data = {
        "users" : "John Doe",
        "profile_img" : "https://placehold.co/600x400",
        "location" : ["Bangkok", "Nonthaburi"],
        "date_from" : "01 Jan 2025",
        "date_to" : "31 Dec 2025",
        "overview_data" : {
    "transactions_total": 88,
    "transactions_approved": 35,
    "key_indicators": {
        "total_waste": 11121.053899999999,
        "recycle_rate": 51.03881296717751,
        "ghg_reduction": 7720.828229899999
    },
    "top_recyclables": [
        {
            "origin_id": 2444,
            "origin_name": "Floor 1",
            "total_waste": 2473
        },
        {
            "origin_id": 2462,
            "origin_name": "Building 2",
            "total_waste": 922
        },
        {
            "origin_id": 2499,
            "origin_name": "Room 5",
            "total_waste": 668.536
        },
        {
            "origin_id": 2481,
            "origin_name": "Building 3",
            "total_waste": 650
        },
        {
            "origin_id": 2469,
            "origin_name": "Floor 2",
            "total_waste": 500
        }
    ],
    "overall_charts": {
        "chart_stat_data": [
            {
                "title": "Total Recyclables",
                "value": 5676.0539
            },
            {
                "title": "Number of Trees",
                "value": 81271.87610421052
            },
            {
                "title": "Plastic Saved",
                "value": 1917.0357
            }
        ],
        "chart_data": {
            "2024": [
                {
                    "month": "Jan",
                    "value": 1206
                },
                {
                    "month": "Feb",
                    "value": 728
                },
                {
                    "month": "Mar",
                    "value": 229
                },
                {
                    "month": "Apr",
                    "value": 29
                },
                {
                    "month": "May",
                    "value": 362
                },
                {
                    "month": "Jun",
                    "value": 430
                },
                {
                    "month": "Jul",
                    "value": 201
                },
                {
                    "month": "Aug",
                    "value": 167
                },
                {
                    "month": "Sep",
                    "value": 828
                },
                {
                    "month": "Oct",
                    "value": 13
                },
                {
                    "month": "Nov",
                    "value": 126
                },
                {
                    "month": "Dec",
                    "value": 231
                }
            ],
            "2025": [
                {
                    "month": "Jan",
                    "value": 68
                },
                {
                    "month": "Feb",
                    "value": 464
                },
                {
                    "month": "Mar",
                    "value": 433
                },
                {
                    "month": "Apr",
                    "value": 500
                },
                {
                    "month": "May",
                    "value": 846
                },
                {
                    "month": "Jun",
                    "value": 1003
                },
                {
                    "month": "Jul",
                    "value": 379
                },
                {
                    "month": "Aug",
                    "value": 53
                },
                {
                    "month": "Sep",
                    "value": 724
                },
                {
                    "month": "Oct",
                    "value": 455
                },
                {
                    "month": "Nov",
                    "value": 1646.05
                }
            ],
            "2026": [
                {
                    "month": "Jan",
                    "value": 68
                },
                {
                    "month": "Feb",
                    "value": 464
                },
                {
                    "month": "Mar",
                    "value": 433
                },
                {
                    "month": "Apr",
                    "value": 500
                },
                {
                    "month": "May",
                    "value": 846
                },
                {
                    "month": "Jun",
                    "value": 1003
                },
                {
                    "month": "Jul",
                    "value": 379
                },
                {
                    "month": "Aug",
                    "value": 53
                },
                {
                    "month": "Sep",
                    "value": 724
                },
                {
                    "month": "Oct",
                    "value": 455
                },
                {
                    "month": "Nov",
                    "value": 1646.05
                }
            ]
        }
    },
    "waste_type_proportions": [
        {
            "category_id": 3,
            "category_name": "Organic Waste",
            "total_waste": 2939,
            "proportion_percent": 26.427351458120352
        },
        {
            "category_id": 1,
            "category_name": "Recyclable Waste",
            "total_waste": 2737.0539,
            "proportion_percent": 24.611461509057158
        },
        {
            "category_id": 7,
            "category_name": "Construction Waste",
            "total_waste": 2580,
            "proportion_percent": 23.19924013676438
        },
        {
            "category_id": 4,
            "category_name": "General Waste",
            "total_waste": 1720,
            "proportion_percent": 15.466160091176251
        },
        {
            "category_id": 2,
            "category_name": "Electronic Waste",
            "total_waste": 578,
            "proportion_percent": 5.197349146918532
        },
        {
            "category_id": 5,
            "category_name": "Hazardous Waste",
            "total_waste": 287,
            "proportion_percent": 2.5806906663765026
        },
        {
            "category_id": 9,
            "category_name": "Waste To Energy",
            "total_waste": 275,
            "proportion_percent": 2.4727872238799242
        },
        {
            "category_id": 6,
            "category_name": "Bio-Hazardous Waste",
            "total_waste": 5,
            "proportion_percent": 0.04495976770690771
        }
    ],
    "material_summary": []
    },
    "comparison_data" : {
    "left": {
        "period" : "Q1 2024",
        "material": {
            "Construction Waste": 1130,
            "Organic Waste": 1125,
            "Recyclable Waste": 730,
            "General Waste": 678,
            "Electronic Waste": 527,
            "Waste To Energy": 225,
            "Hazardous Waste": 131,
            "Bio-Hazardous Waste": 4
        },
        "month": {
            "Jan": 1206,
            "Feb": 728,
            "Mar": 229,
            "Apr": 29,
            "May": 362,
            "Jun": 430,
            "Jul": 201,
            "Aug": 167,
            "Sep": 828,
            "Oct": 13,
            "Nov": 126,
            "Dec": 231
        },
        "total_waste_kg": 4550
    },
    "right": {
        "period" : "Q1 2025",
        "material": {
            "Recyclable Waste": 2164.2,
            "Organic Waste": 1814,
            "Construction Waste": 1450,
            "General Waste": 1042,
            "Hazardous Waste": 156,
            "Electronic Waste": 51,
            "Waste To Energy": 50,
            "Bio-Hazardous Waste": 1
        },
        "month": {
            "Jan": 68,
            "Feb": 464,
            "Mar": 433,
            "Apr": 500,
            "May": 846,
            "Jun": 1003,
            "Jul": 379,
            "Aug": 53,
            "Sep": 724,
            "Oct": 455,
            "Nov": 1803.2,
            "Dec": 0
        },
        "total_waste_kg": 6728.2
    },
    "scores": {
        "opportunities": [
            {
                "id": 2,
                "condition_name": "Circular_Economy_Foundation",
                "criterior": "circular_economy_score > -20 AND resource_recovery_potential > -50",
                "urgency_score": 4748.6,
                "variables": {
                    "resource_recovery_potential": 2494.2,
                    "circular_economy_score": 2184.4
                },
                "materials_used": [
                    "construction",
                    "general",
                    "organic",
                    "recyclable"
                ],
                "risk_problems": "Good foundation for circular economy initiatives. Material recovery systems partially functional. Opportunity to dramatically improve by closing material loops and increasing recovery rates.",
                "recommendation": "Identify opportunities to use recovered materials internally or sell to other organizations. Establish partnerships for material exchanges. Implement 'design for recycling' principles in procurement. Create reverse logistics for packaging materials from suppliers. Consider establishing material recovery facility or partnership. Showcase circular success stories.",
                "weighted_urgency": 4748.6,
                "urgency_normalized": 100,
                "priority": "high"
            },
            {
                "id": 1,
                "condition_name": "High_Recyclable_Potential",
                "criterior": "recycling_efficiency_score > -20 AND recyclable_recovery_momentum > -30 AND waste_segregation_quality > -0.10",
                "urgency_score": 3486.86,
                "variables": {
                    "recyclable_recovery_momentum": 2184.4,
                    "waste_segregation_quality": 0.16,
                    "recycling_efficiency_score": 1252.2
                },
                "materials_used": [
                    "construction",
                    "general",
                    "recyclable"
                ],
                "risk_problems": "Recycling metrics stable or slightly declining but significant room for improvement. Current segregation adequate foundation for expansion. Untapped recyclable materials likely in general waste. Revenue opportunity from increased recycling.",
                "recommendation": "Conduct waste composition audit to quantify recyclables in general waste. Expand recycling categories if infrastructure allows (plastics #3-7, textiles, specialty materials). Pilot advanced segregation in high-performing areas first. Partner with recycling vendor for revenue share arrangement. Market the environmental and financial benefits internally.",
                "weighted_urgency": 3486.86,
                "urgency_normalized": 73.43,
                "priority": "medium"
            }
        ],
        "quickwins": [
            {
                "id": 20,
                "condition_name": "Bulk_Purchasing_Initiative",
                "criterior": "waste_prevention_effectiveness < -80 AND overall_waste_reduction_rate < -120 AND general_waste_minimization < -60",
                "urgency_score": 2509.2,
                "variables": {
                    "general_waste_minimization": -364,
                    "waste_prevention_effectiveness": -230,
                    "overall_waste_reduction_rate": -2175.2
                },
                "materials_used": [
                    "bio_hazardous",
                    "construction",
                    "electronic",
                    "general",
                    "hazardous",
                    "organic",
                    "recyclable",
                    "waste_to_energy"
                ],
                "risk_problems": "Waste increasing, likely includes single-serve packaging. Bulk purchasing dramatically reduces packaging waste. Often cost-neutral or cost-saving. Quick procurement policy change.",
                "recommendation": "Identify bulk purchasing opportunities: beverages, snacks, supplies, cleaning products. Install dispensers as needed. Calculate packaging reduction and cost savings. Communicate benefits. Budget: ~$2000-8000 (dispensers, initial bulk products), Timeline: 4-6 weeks, Impact: 20-40% packaging waste reduction in targeted categories.",
                "weighted_urgency": 2509.2,
                "urgency_normalized": 52.84,
                "priority": "medium"
            },
            {
                "id": 24,
                "condition_name": "Landscape_Waste_On_Site_Mulching",
                "criterior": "organic_diversion_score > 100 AND construction_volume_impact < 0 AND organic_processing_efficiency < -60",
                "urgency_score": 1910.8,
                "variables": {
                    "construction_volume_impact": -552.8,
                    "organic_diversion_score": 741.5,
                    "organic_processing_efficiency": -776.5
                },
                "materials_used": [
                    "construction",
                    "general",
                    "organic",
                    "waste_to_energy"
                ],
                "risk_problems": "Significant landscaping waste hauled away. On-site mulching eliminates hauling costs and provides valuable mulch for landscaping use. Quick ROI on chipper/mower if volume sufficient.",
                "recommendation": "Evaluate landscape waste volume and mulching equipment ROI. Chip woody waste on-site. Mulch-mow grass clippings. Use mulch in landscaping (free, no hauling). Consider small chipper ($2-5K) or mulching mowers ($500-2K). Budget: ~$2000-8000 (equipment), Timeline: immediate, Impact: 60-100% landscape waste diversion + cost savings + better landscaping.",
                "weighted_urgency": 1910.8,
                "urgency_normalized": 40.24,
                "priority": "low"
            }
        ],
        "risks": [
            {
                "id": 18,
                "condition_name": "Organic_Methane_Risk",
                "criterior": "organic_diversion_score > 200 AND overall_waste_reduction_rate < -150",
                "urgency_score": 2566.7,
                "variables": {
                    "organic_diversion_score": 741.5,
                    "overall_waste_reduction_rate": -2175.2
                },
                "materials_used": [
                    "bio_hazardous",
                    "construction",
                    "electronic",
                    "general",
                    "hazardous",
                    "organic",
                    "recyclable",
                    "waste_to_energy"
                ],
                "risk_problems": "Organic waste surging >150kg without diversion infrastructure. If landfilled, generates potent methane greenhouse gas. Missed compost/energy value. Indicates food service, landscaping, or packaging changes without waste planning.",
                "recommendation": "Immediately segregate organics from general waste to prevent methane generation. Emergency partnership with composting or anaerobic digestion facility. Source reduction focus: food waste prevention, menu planning, portion control if cafeteria. Consider on-site dehydration or grinding to reduce volume and improve handling. Evaluate packaging alternatives.",
                "weighted_urgency": 2566.7,
                "urgency_normalized": 54.05,
                "priority": "medium"
            },
            {
                "id": 2,
                "condition_name": "General_Waste_Trend_Rising",
                "criterior": "overall_waste_reduction_rate < -200 AND general_waste_minimization < -100",
                "urgency_score": 2239.2,
                "variables": {
                    "general_waste_minimization": -364,
                    "overall_waste_reduction_rate": -2175.2
                },
                "materials_used": [
                    "bio_hazardous",
                    "construction",
                    "electronic",
                    "general",
                    "hazardous",
                    "organic",
                    "recyclable",
                    "waste_to_energy"
                ],
                "risk_problems": "Total waste generation increasing by >200kg with general waste rising >100kg. Indicates systematic breakdown in waste management. Rising operational costs and environmental footprint. May signal process inefficiencies or lack of staff awareness.",
                "recommendation": "Conduct comprehensive waste audit to identify major sources. Review operational changes in recent period. Implement immediate waste tracking and measurement systems. Schedule staff training on waste segregation and reduction. Set departmental waste reduction targets.",
                "weighted_urgency": 2239.2,
                "urgency_normalized": 47.15,
                "priority": "low"
            }
        ]
    },
},
"main_materials_data" : {
    "porportions": [
        {
            "main_material_id": 10,
            "main_material_name": "Food and Plant Waste",
            "total_waste": 1814,
            "ghg_reduction": 1473.0800000000002,
            "proportion_percent": 26.961140984785253
        },
        {
            "main_material_id": 1,
            "main_material_name": "Plastic",
            "total_waste": 1619.1837,
            "ghg_reduction": 1617.8283946999995,
            "proportion_percent": 24.065622941546984
        },
        {
            "main_material_id": 5,
            "main_material_name": "Metal",
            "total_waste": 867,
            "ghg_reduction": 144.62900000000002,
            "proportion_percent": 12.8860580120225
        },
        {
            "main_material_id": 11,
            "main_material_name": "General Waste",
            "total_waste": 856,
            "ghg_reduction": 0,
            "proportion_percent": 12.722567079920713
        },
        {
            "main_material_id": 32,
            "main_material_name": "Concrete",
            "total_waste": 650,
            "ghg_reduction": 0,
            "proportion_percent": 9.66082780601456
        },
        {
            "main_material_id": 4,
            "main_material_name": "Paper",
            "total_waste": 325,
            "ghg_reduction": 1844.0500000000002,
            "proportion_percent": 4.83041390300728
        },
        {
            "main_material_id": 28,
            "main_material_name": "Non-Specific General Waste",
            "total_waste": 175,
            "ghg_reduction": 0,
            "proportion_percent": 2.6009921016193047
        },
        {
            "main_material_id": 2,
            "main_material_name": "Glass",
            "total_waste": 118.4182,
            "ghg_reduction": 32.6834232,
            "proportion_percent": 1.7600274450741435
        },
        {
            "main_material_id": 18,
            "main_material_name": "Chemicals and Liquids",
            "total_waste": 85,
            "ghg_reduction": 0,
            "proportion_percent": 1.2633390207865196
        },
        {
            "main_material_id": 33,
            "main_material_name": "Non-Specific Recyclables",
            "total_waste": 84.6,
            "ghg_reduction": 196.272,
            "proportion_percent": 1.2573938959828181
        },
        {
            "main_material_id": 23,
            "main_material_name": "Bulbs",
            "total_waste": 70,
            "ghg_reduction": 0,
            "proportion_percent": 1.040396840647722
        },
        {
            "main_material_id": 9,
            "main_material_name": "Electrical Wire",
            "total_waste": 31,
            "ghg_reduction": 0,
            "proportion_percent": 0.4607471722868483
        },
        {
            "main_material_id": 8,
            "main_material_name": "Electrical Appliances",
            "total_waste": 20,
            "ghg_reduction": 0,
            "proportion_percent": 0.2972562401850634
        },
        {
            "main_material_id": 14,
            "main_material_name": "Wood",
            "total_waste": 11,
            "ghg_reduction": 0,
            "proportion_percent": 0.16349093210178486
        },
        {
            "main_material_id": 13,
            "main_material_name": "Batteries",
            "total_waste": 1,
            "ghg_reduction": 0,
            "proportion_percent": 0.014862812009253172
        },
        {
            "main_material_id": 17,
            "main_material_name": "Personal Items",
            "total_waste": 1,
            "ghg_reduction": 0,
            "proportion_percent": 0.014862812009253172
        }
    ],
    "total_waste": 6728.2019
    },
    "performance_data" : [
    {
        "id": "2277",
        "totalWasteKg": 5339,
        "metrics": {
            "Recyclable Waste": 572,
            "Organic Waste": 437,
            "Electronic Waste": 1052,
            "Bio-Hazardous Waste": 776,
            "Hazardous Waste": 746,
            "Waste To Energy": 703,
            "General Waste": 1053
        },
        "recyclingRatePercent": 18.9,
        "recyclable_weight": 1009,
        "general_weight": 1053,
        "branchName": "Branch 1",
        "buildings": [
            {
                "id": "2278",
                "totalWasteKg": 2103,
                "metrics": {
                    "Organic Waste": 181,
                    "Electronic Waste": 408,
                    "Bio-Hazardous Waste": 459,
                    "Recyclable Waste": 197,
                    "Hazardous Waste": 398,
                    "Waste To Energy": 287,
                    "General Waste": 173
                },
                "buildingName": "Building 1",
                "floors": [
                    {
                        "id": "2279",
                        "totalWasteKg": 1159,
                        "metrics": {
                            "Organic Waste": 48,
                            "Electronic Waste": 255,
                            "Bio-Hazardous Waste": 312,
                            "Recyclable Waste": 134,
                            "Hazardous Waste": 162,
                            "Waste To Energy": 123,
                            "General Waste": 125
                        },
                        "floorName": "Floor 1",
                        "rooms": [
                            {
                                "id": "2280",
                                "totalWasteKg": 1159,
                                "metrics": {
                                    "Organic Waste": 48,
                                    "Electronic Waste": 255,
                                    "Bio-Hazardous Waste": 312,
                                    "Recyclable Waste": 134,
                                    "Hazardous Waste": 162,
                                    "Waste To Energy": 123,
                                    "General Waste": 125
                                },
                                "roomName": "Room 1"
                            }
                        ]
                    },
                    {
                        "id": "2282",
                        "totalWasteKg": 944,
                        "metrics": {
                            "Hazardous Waste": 236,
                            "Waste To Energy": 164,
                            "Recyclable Waste": 63,
                            "Electronic Waste": 153,
                            "Organic Waste": 133,
                            "General Waste": 48,
                            "Bio-Hazardous Waste": 147
                        },
                        "floorName": "Floor 2",
                        "rooms": [
                            {
                                "id": "2284",
                                "totalWasteKg": 944,
                                "metrics": {
                                    "Hazardous Waste": 236,
                                    "Waste To Energy": 164,
                                    "Recyclable Waste": 63,
                                    "Electronic Waste": 153,
                                    "Organic Waste": 133,
                                    "General Waste": 48,
                                    "Bio-Hazardous Waste": 147
                                },
                                "roomName": "Room 2"
                            }
                        ]
                    }
                ]
            },
            {
                "id": "2285",
                "totalWasteKg": 3076,
                "metrics": {
                    "Waste To Energy": 416,
                    "Electronic Waste": 644,
                    "Organic Waste": 256,
                    "Recyclable Waste": 215,
                    "General Waste": 880,
                    "Hazardous Waste": 348,
                    "Bio-Hazardous Waste": 317
                },
                "buildingName": "Building 2",
                "floors": [
                    {
                        "id": "2286",
                        "totalWasteKg": 2313,
                        "metrics": {
                            "Waste To Energy": 416,
                            "Electronic Waste": 644,
                            "Organic Waste": 234,
                            "Recyclable Waste": 215,
                            "General Waste": 262,
                            "Hazardous Waste": 348,
                            "Bio-Hazardous Waste": 194
                        },
                        "floorName": "Floor 1",
                        "rooms": [
                            {
                                "id": "2288",
                                "totalWasteKg": 2313,
                                "metrics": {
                                    "Waste To Energy": 416,
                                    "Electronic Waste": 644,
                                    "Organic Waste": 234,
                                    "Recyclable Waste": 215,
                                    "General Waste": 262,
                                    "Hazardous Waste": 348,
                                    "Bio-Hazardous Waste": 194
                                },
                                "roomName": "Room 2"
                            }
                        ]
                    },
                    {
                        "id": "2289",
                        "totalWasteKg": 763,
                        "metrics": {
                            "Bio-Hazardous Waste": 123,
                            "Organic Waste": 22,
                            "General Waste": 618
                        },
                        "floorName": "Floor 2",
                        "rooms": [
                            {
                                "id": "2291",
                                "totalWasteKg": 763,
                                "metrics": {
                                    "Bio-Hazardous Waste": 123,
                                    "Organic Waste": 22,
                                    "General Waste": 618
                                },
                                "roomName": "Room 2"
                            }
                        ]
                    }
                ]
            }
        ]
    },
    {
        "id": "2307",
        "totalWasteKg": 2001,
        "metrics": {
            "General Waste": 817,
            "Hazardous Waste": 199,
            "Bio-Hazardous Waste": 158,
            "Waste To Energy": 293,
            "Recyclable Waste": 175,
            "Electronic Waste": 261,
            "Organic Waste": 98
        },
        "recyclingRatePercent": 13.64,
        "recyclable_weight": 273,
        "general_weight": 817,
        "branchName": "Branch 3",
        "buildings": [
            {
                "id": "2308",
                "totalWasteKg": 930,
                "metrics": {
                    "General Waste": 565,
                    "Hazardous Waste": 76,
                    "Bio-Hazardous Waste": 42,
                    "Waste To Energy": 51,
                    "Recyclable Waste": 61,
                    "Electronic Waste": 123,
                    "Organic Waste": 12
                },
                "buildingName": "Building 1",
                "floors": [
                    {
                        "id": "2309",
                        "totalWasteKg": 930,
                        "metrics": {
                            "General Waste": 565,
                            "Hazardous Waste": 76,
                            "Bio-Hazardous Waste": 42,
                            "Waste To Energy": 51,
                            "Recyclable Waste": 61,
                            "Electronic Waste": 123,
                            "Organic Waste": 12
                        },
                        "floorName": "Floor 1",
                        "rooms": [
                            {
                                "id": "2310",
                                "totalWasteKg": 930,
                                "metrics": {
                                    "General Waste": 565,
                                    "Hazardous Waste": 76,
                                    "Bio-Hazardous Waste": 42,
                                    "Waste To Energy": 51,
                                    "Recyclable Waste": 61,
                                    "Electronic Waste": 123,
                                    "Organic Waste": 12
                                },
                                "roomName": "Room 1"
                            }
                        ]
                    }
                ]
            },
            {
                "id": "2315",
                "totalWasteKg": 1071,
                "metrics": {
                    "Hazardous Waste": 123,
                    "Bio-Hazardous Waste": 116,
                    "Waste To Energy": 242,
                    "Electronic Waste": 138,
                    "Recyclable Waste": 114,
                    "Organic Waste": 86,
                    "General Waste": 252
                },
                "buildingName": "Building 2",
                "floors": [
                    {
                        "id": "2316",
                        "totalWasteKg": 1071,
                        "metrics": {
                            "Hazardous Waste": 123,
                            "Bio-Hazardous Waste": 116,
                            "Waste To Energy": 242,
                            "Electronic Waste": 138,
                            "Recyclable Waste": 114,
                            "Organic Waste": 86,
                            "General Waste": 252
                        },
                        "floorName": "Floor 1",
                        "rooms": [
                            {
                                "id": "2317",
                                "totalWasteKg": 596,
                                "metrics": {
                                    "Hazardous Waste": 123,
                                    "Bio-Hazardous Waste": 116,
                                    "Waste To Energy": 242,
                                    "Electronic Waste": 63,
                                    "Recyclable Waste": 52
                                },
                                "roomName": "Room 1"
                            },
                            {
                                "id": "2318",
                                "totalWasteKg": 475,
                                "metrics": {
                                    "Recyclable Waste": 62,
                                    "Electronic Waste": 75,
                                    "Organic Waste": 86,
                                    "General Waste": 252
                                },
                                "roomName": "Room 2"
                            }
                        ]
                    }
                ]
            }
        ]
    },
    {
        "id": "2322",
        "totalWasteKg": 2703,
        "metrics": {
            "Bio-Hazardous Waste": 560,
            "Waste To Energy": 194,
            "Recyclable Waste": 322,
            "Electronic Waste": 116,
            "Organic Waste": 738,
            "General Waste": 298,
            "Hazardous Waste": 475
        },
        "recyclingRatePercent": 39.22,
        "recyclable_weight": 1060,
        "general_weight": 298,
        "branchName": "Branch 4",
        "buildings": [
            {
                "id": "2323",
                "totalWasteKg": 1273,
                "metrics": {
                    "Bio-Hazardous Waste": 101,
                    "Waste To Energy": 96,
                    "Recyclable Waste": 175,
                    "Electronic Waste": 41,
                    "Organic Waste": 515,
                    "General Waste": 123,
                    "Hazardous Waste": 222
                },
                "buildingName": "Building 1",
                "floors": [
                    {
                        "id": "2327",
                        "totalWasteKg": 1273,
                        "metrics": {
                            "Bio-Hazardous Waste": 101,
                            "Waste To Energy": 96,
                            "Recyclable Waste": 175,
                            "Electronic Waste": 41,
                            "Organic Waste": 515,
                            "General Waste": 123,
                            "Hazardous Waste": 222
                        },
                        "floorName": "Floor 2",
                        "rooms": [
                            {
                                "id": "2329",
                                "totalWasteKg": 1273,
                                "metrics": {
                                    "Bio-Hazardous Waste": 101,
                                    "Waste To Energy": 96,
                                    "Recyclable Waste": 175,
                                    "Electronic Waste": 41,
                                    "Organic Waste": 515,
                                    "General Waste": 123,
                                    "Hazardous Waste": 222
                                },
                                "roomName": "Room 2"
                            }
                        ]
                    }
                ]
            },
            {
                "id": "2330",
                "totalWasteKg": 1430,
                "metrics": {
                    "Hazardous Waste": 253,
                    "Bio-Hazardous Waste": 459,
                    "Recyclable Waste": 147,
                    "Electronic Waste": 75,
                    "Organic Waste": 223,
                    "General Waste": 175,
                    "Waste To Energy": 98
                },
                "buildingName": "Building 2",
                "floors": [
                    {
                        "id": "2331",
                        "totalWasteKg": 882,
                        "metrics": {
                            "Hazardous Waste": 130,
                            "Bio-Hazardous Waste": 407,
                            "Recyclable Waste": 54,
                            "Electronic Waste": 23,
                            "Organic Waste": 123,
                            "General Waste": 111,
                            "Waste To Energy": 34
                        },
                        "floorName": "Floor 1",
                        "rooms": [
                            {
                                "id": "2333",
                                "totalWasteKg": 882,
                                "metrics": {
                                    "Hazardous Waste": 130,
                                    "Bio-Hazardous Waste": 407,
                                    "Recyclable Waste": 54,
                                    "Electronic Waste": 23,
                                    "Organic Waste": 123,
                                    "General Waste": 111,
                                    "Waste To Energy": 34
                                },
                                "roomName": "Room 2"
                            }
                        ]
                    },
                    {
                        "id": "2334",
                        "totalWasteKg": 548,
                        "metrics": {
                            "General Waste": 64,
                            "Hazardous Waste": 123,
                            "Bio-Hazardous Waste": 52,
                            "Waste To Energy": 64,
                            "Recyclable Waste": 93,
                            "Electronic Waste": 52,
                            "Organic Waste": 100
                        },
                        "floorName": "Floor 2",
                        "rooms": [
                            {
                                "id": "2335",
                                "totalWasteKg": 548,
                                "metrics": {
                                    "General Waste": 64,
                                    "Hazardous Waste": 123,
                                    "Bio-Hazardous Waste": 52,
                                    "Waste To Energy": 64,
                                    "Recyclable Waste": 93,
                                    "Electronic Waste": 52,
                                    "Organic Waste": 100
                                },
                                "roomName": "Room 1"
                            }
                        ]
                    }
                ]
            }
        ]
    }
],
"sub_materials_data": 
    {
    "porportions": [
        {
            "material_id": 77,
            "material_name": "Foodwaste",
            "main_material_id": 10,
            "total_waste": 1074,
            "ghg_reduction": 499.41,
            "proportion_percent": 15.962660097937906
        },
        {
            "material_id": 94,
            "material_name": "General Waste",
            "main_material_id": 11,
            "total_waste": 856,
            "ghg_reduction": 0,
            "proportion_percent": 12.722567079920713
        },
        {
            "material_id": 244,
            "material_name": "Pile Head",
            "main_material_id": 5,
            "total_waste": 800,
            "ghg_reduction": 0,
            "proportion_percent": 11.890249607402536
        },
        {
            "material_id": 245,
            "material_name": "Concrete",
            "main_material_id": 32,
            "total_waste": 650,
            "ghg_reduction": 0,
            "proportion_percent": 9.66082780601456
        },
        {
            "material_id": 78,
            "material_name": "Leaves Trees",
            "main_material_id": 10,
            "total_waste": 450,
            "ghg_reduction": 384.3,
            "proportion_percent": 6.688265404163926
        },
        {
            "material_id": 1,
            "material_name": "Clear Plastic (PET)",
            "main_material_id": 1,
            "total_waste": 433.24,
            "ghg_reduction": 446.6704400000001,
            "proportion_percent": 6.439164674888843
        },
        {
            "material_id": 118,
            "material_name": "Other PVC Pipes",
            "main_material_id": 1,
            "total_waste": 394,
            "ghg_reduction": 406.21399999999994,
            "proportion_percent": 5.855947931645749
        },
        {
            "material_id": 2,
            "material_name": "Opague Plastic (HDPE)",
            "main_material_id": 1,
            "total_waste": 389.66769999999997,
            "ghg_reduction": 401.7473987,
            "proportion_percent": 5.791557771178061
        },
        {
            "material_id": 308,
            "material_name": "Food Surplus",
            "main_material_id": 10,
            "total_waste": 220,
            "ghg_reduction": 556.82,
            "proportion_percent": 3.2698186420356974
        },
        {
            "material_id": 186,
            "material_name": "Waste to Landfill",
            "main_material_id": 28,
            "total_waste": 175,
            "ghg_reduction": 0,
            "proportion_percent": 2.6009921016193047
        },
        {
            "material_id": 129,
            "material_name": "Paper Cores",
            "main_material_id": 4,
            "total_waste": 154,
            "ghg_reduction": 873.796,
            "proportion_percent": 2.2888730494249883
        },
        {
            "material_id": 39,
            "material_name": "Brown Paper Box / Carton / Cardboard",
            "main_material_id": 4,
            "total_waste": 127,
            "ghg_reduction": 720.5980000000001,
            "proportion_percent": 1.8875771251751525
        },
        {
            "material_id": 272,
            "material_name": "Mixed color plastic (PET)",
            "main_material_id": 1,
            "total_waste": 102,
            "ghg_reduction": 105.16199999999999,
            "proportion_percent": 1.5160068249438234
        },
        {
            "material_id": 23,
            "material_name": "LEO (12 bottle Carton)",
            "main_material_id": 2,
            "total_waste": 99.4182,
            "ghg_reduction": 27.4394232,
            "proportion_percent": 1.4776340168983335
        },
        {
            "material_id": 298,
            "material_name": "Recyclables",
            "main_material_id": 33,
            "total_waste": 84.6,
            "ghg_reduction": 196.272,
            "proportion_percent": 1.2573938959828181
        },
        {
            "material_id": 307,
            "material_name": "PET Cup",
            "main_material_id": 1,
            "total_waste": 76,
            "ghg_reduction": 78.356,
            "proportion_percent": 1.1295737127032408
        },
        {
            "material_id": 105,
            "material_name": "Damaged bulb",
            "main_material_id": 23,
            "total_waste": 70,
            "ghg_reduction": 0,
            "proportion_percent": 1.040396840647722
        },
        {
            "material_id": 195,
            "material_name": "Black Plastic",
            "main_material_id": 1,
            "total_waste": 65,
            "ghg_reduction": 67.015,
            "proportion_percent": 0.9660827806014561
        },
        {
            "material_id": 133,
            "material_name": "Steel Scrap",
            "main_material_id": 5,
            "total_waste": 52,
            "ghg_reduction": 95.26400000000001,
            "proportion_percent": 0.7728662244811649
        },
        {
            "material_id": 306,
            "material_name": "Plate waste",
            "main_material_id": 10,
            "total_waste": 50,
            "ghg_reduction": 23.25,
            "proportion_percent": 0.7431406004626585
        },
        {
            "material_id": 159,
            "material_name": "Multilayer packaging (Waste to energy)",
            "main_material_id": 1,
            "total_waste": 50,
            "ghg_reduction": 0,
            "proportion_percent": 0.7431406004626585
        },
        {
            "material_id": 206,
            "material_name": "Hazardous Chemicals",
            "main_material_id": 18,
            "total_waste": 43,
            "ghg_reduction": 0,
            "proportion_percent": 0.6391009163978864
        },
        {
            "material_id": 144,
            "material_name": "Contaminated containers",
            "main_material_id": 18,
            "total_waste": 42,
            "ghg_reduction": 0,
            "proportion_percent": 0.6242381043886333
        },
        {
            "material_id": 289,
            "material_name": "PET with label",
            "main_material_id": 1,
            "total_waste": 35,
            "ghg_reduction": 36.084999999999994,
            "proportion_percent": 0.520198420323861
        },
        {
            "material_id": 5,
            "material_name": "Foam",
            "main_material_id": 1,
            "total_waste": 31.816,
            "ghg_reduction": 32.80229599999999,
            "proportion_percent": 0.4728752268863988
        },
        {
            "material_id": 304,
            "material_name": "LAN Cable",
            "main_material_id": 9,
            "total_waste": 31,
            "ghg_reduction": 0,
            "proportion_percent": 0.4607471722868483
        },
        {
            "material_id": 46,
            "material_name": "Mixed Paper",
            "main_material_id": 4,
            "total_waste": 25,
            "ghg_reduction": 141.85000000000002,
            "proportion_percent": 0.37157030023132925
        },
        {
            "material_id": 114,
            "material_name": "Vegetable Cooking Oil",
            "main_material_id": 10,
            "total_waste": 20,
            "ghg_reduction": 9.3,
            "proportion_percent": 0.2972562401850634
        },
        {
            "material_id": 64,
            "material_name": "Computer accessories",
            "main_material_id": 8,
            "total_waste": 20,
            "ghg_reduction": 0,
            "proportion_percent": 0.2972562401850634
        },
        {
            "material_id": 223,
            "material_name": "Document Folder",
            "main_material_id": 4,
            "total_waste": 19,
            "ghg_reduction": 107.80600000000001,
            "proportion_percent": 0.2823934281758102
        },
        {
            "material_id": 22,
            "material_name": "Colored Glass (Bottle)",
            "main_material_id": 2,
            "total_waste": 19,
            "ghg_reduction": 5.244000000000001,
            "proportion_percent": 0.2823934281758102
        },
        {
            "material_id": 9,
            "material_name": "CD DVD",
            "main_material_id": 1,
            "total_waste": 16.368000000000002,
            "ghg_reduction": 16.875408,
            "proportion_percent": 0.24327450696745592
        },
        {
            "material_id": 55,
            "material_name": "Stainless Steel",
            "main_material_id": 5,
            "total_waste": 12,
            "ghg_reduction": 21.984,
            "proportion_percent": 0.17835374411103805
        },
        {
            "material_id": 286,
            "material_name": "Wood (General Waste)",
            "main_material_id": 14,
            "total_waste": 11,
            "ghg_reduction": 0,
            "proportion_percent": 0.16349093210178486
        },
        {
            "material_id": 285,
            "material_name": "Ice Bucket",
            "main_material_id": 1,
            "total_waste": 5,
            "ghg_reduction": 5.154999999999999,
            "proportion_percent": 0.07431406004626585
        },
        {
            "material_id": 273,
            "material_name": "Transparent HDPE with screening",
            "main_material_id": 1,
            "total_waste": 5,
            "ghg_reduction": 5.154999999999999,
            "proportion_percent": 0.07431406004626585
        },
        {
            "material_id": 191,
            "material_name": "Nylon Net",
            "main_material_id": 1,
            "total_waste": 5,
            "ghg_reduction": 5.154999999999999,
            "proportion_percent": 0.07431406004626585
        },
        {
            "material_id": 3,
            "material_name": "Plastic Bag",
            "main_material_id": 1,
            "total_waste": 4.092,
            "ghg_reduction": 4.218851999999999,
            "proportion_percent": 0.06081862674186397
        },
        {
            "material_id": 150,
            "material_name": "Stretch Film",
            "main_material_id": 1,
            "total_waste": 3,
            "ghg_reduction": 3.093,
            "proportion_percent": 0.04458843602775951
        },
        {
            "material_id": 284,
            "material_name": "Aluminium Radiator",
            "main_material_id": 5,
            "total_waste": 2,
            "ghg_reduction": 18.254,
            "proportion_percent": 0.029725624018506345
        },
        {
            "material_id": 287,
            "material_name": "Screened color PET",
            "main_material_id": 1,
            "total_waste": 2,
            "ghg_reduction": 2.062,
            "proportion_percent": 0.029725624018506345
        },
        {
            "material_id": 4,
            "material_name": "PVC Pipes Green",
            "main_material_id": 1,
            "total_waste": 1,
            "ghg_reduction": 1.031,
            "proportion_percent": 0.014862812009253172
        },
        {
            "material_id": 109,
            "material_name": "Old batteries",
            "main_material_id": 13,
            "total_waste": 1,
            "ghg_reduction": 0,
            "proportion_percent": 0.014862812009253172
        },
        {
            "material_id": 75,
            "material_name": "Aluminum Can (Kg)",
            "main_material_id": 5,
            "total_waste": 1,
            "ghg_reduction": 9.127,
            "proportion_percent": 0.014862812009253172
        },
        {
            "material_id": 255,
            "material_name": "Antigen Test Kit (ATK)",
            "main_material_id": 17,
            "total_waste": 1,
            "ghg_reduction": 0,
            "proportion_percent": 0.014862812009253172
        },
        {
            "material_id": 260,
            "material_name": "Other Plastic LDPE",
            "main_material_id": 1,
            "total_waste": 1,
            "ghg_reduction": 1.031,
            "proportion_percent": 0.014862812009253172
        },
        {
            "material_id": 7,
            "material_name": "Breakable Plastic (PS)",
            "main_material_id": 1,
            "total_waste": 0,
            "ghg_reduction": 0,
            "proportion_percent": 0
        },
        {
            "material_id": 11,
            "material_name": "Boots",
            "main_material_id": 1,
            "total_waste": 0,
            "ghg_reduction": 0,
            "proportion_percent": 0
        }
    ],
    "porportions_grouped": {
        "Food and Plant Waste": [
            {
                "material_id": 77,
                "material_name": "Foodwaste",
                "total_waste": 1074,
                "ghg_reduction": 499.41,
                "proportion_percent": 15.962660097937906
            },
            {
                "material_id": 78,
                "material_name": "Leaves Trees",
                "total_waste": 450,
                "ghg_reduction": 384.3,
                "proportion_percent": 6.688265404163926
            },
            {
                "material_id": 308,
                "material_name": "Food Surplus",
                "total_waste": 220,
                "ghg_reduction": 556.82,
                "proportion_percent": 3.2698186420356974
            },
            {
                "material_id": 306,
                "material_name": "Plate waste",
                "total_waste": 50,
                "ghg_reduction": 23.25,
                "proportion_percent": 0.7431406004626585
            },
            {
                "material_id": 114,
                "material_name": "Vegetable Cooking Oil",
                "total_waste": 20,
                "ghg_reduction": 9.3,
                "proportion_percent": 0.2972562401850634
            }
        ],
        "General Waste": [
            {
                "material_id": 94,
                "material_name": "General Waste",
                "total_waste": 856,
                "ghg_reduction": 0,
                "proportion_percent": 12.722567079920713
            }
        ],
        "Metal": [
            {
                "material_id": 244,
                "material_name": "Pile Head",
                "total_waste": 800,
                "ghg_reduction": 0,
                "proportion_percent": 11.890249607402536
            },
            {
                "material_id": 133,
                "material_name": "Steel Scrap",
                "total_waste": 52,
                "ghg_reduction": 95.26400000000001,
                "proportion_percent": 0.7728662244811649
            },
            {
                "material_id": 55,
                "material_name": "Stainless Steel",
                "total_waste": 12,
                "ghg_reduction": 21.984,
                "proportion_percent": 0.17835374411103805
            },
            {
                "material_id": 284,
                "material_name": "Aluminium Radiator",
                "total_waste": 2,
                "ghg_reduction": 18.254,
                "proportion_percent": 0.029725624018506345
            },
            {
                "material_id": 75,
                "material_name": "Aluminum Can (Kg)",
                "total_waste": 1,
                "ghg_reduction": 9.127,
                "proportion_percent": 0.014862812009253172
            }
        ],
        "Concrete": [
            {
                "material_id": 245,
                "material_name": "Concrete",
                "total_waste": 650,
                "ghg_reduction": 0,
                "proportion_percent": 9.66082780601456
            }
        ],
        "Plastic": [
            {
                "material_id": 1,
                "material_name": "Clear Plastic (PET)",
                "total_waste": 433.24,
                "ghg_reduction": 446.6704400000001,
                "proportion_percent": 6.439164674888843
            },
            {
                "material_id": 118,
                "material_name": "Other PVC Pipes",
                "total_waste": 394,
                "ghg_reduction": 406.21399999999994,
                "proportion_percent": 5.855947931645749
            },
            {
                "material_id": 2,
                "material_name": "Opague Plastic (HDPE)",
                "total_waste": 389.66769999999997,
                "ghg_reduction": 401.7473987,
                "proportion_percent": 5.791557771178061
            },
            {
                "material_id": 272,
                "material_name": "Mixed color plastic (PET)",
                "total_waste": 102,
                "ghg_reduction": 105.16199999999999,
                "proportion_percent": 1.5160068249438234
            },
            {
                "material_id": 307,
                "material_name": "PET Cup",
                "total_waste": 76,
                "ghg_reduction": 78.356,
                "proportion_percent": 1.1295737127032408
            },
            {
                "material_id": 195,
                "material_name": "Black Plastic",
                "total_waste": 65,
                "ghg_reduction": 67.015,
                "proportion_percent": 0.9660827806014561
            },
            {
                "material_id": 159,
                "material_name": "Multilayer packaging (Waste to energy)",
                "total_waste": 50,
                "ghg_reduction": 0,
                "proportion_percent": 0.7431406004626585
            },
            {
                "material_id": 289,
                "material_name": "PET with label",
                "total_waste": 35,
                "ghg_reduction": 36.084999999999994,
                "proportion_percent": 0.520198420323861
            },
            {
                "material_id": 5,
                "material_name": "Foam",
                "total_waste": 31.816,
                "ghg_reduction": 32.80229599999999,
                "proportion_percent": 0.4728752268863988
            },
            {
                "material_id": 9,
                "material_name": "CD DVD",
                "total_waste": 16.368000000000002,
                "ghg_reduction": 16.875408,
                "proportion_percent": 0.24327450696745592
            },
            {
                "material_id": 285,
                "material_name": "Ice Bucket",
                "total_waste": 5,
                "ghg_reduction": 5.154999999999999,
                "proportion_percent": 0.07431406004626585
            },
            {
                "material_id": 273,
                "material_name": "Transparent HDPE with screening",
                "total_waste": 5,
                "ghg_reduction": 5.154999999999999,
                "proportion_percent": 0.07431406004626585
            },
            {
                "material_id": 191,
                "material_name": "Nylon Net",
                "total_waste": 5,
                "ghg_reduction": 5.154999999999999,
                "proportion_percent": 0.07431406004626585
            },
            {
                "material_id": 3,
                "material_name": "Plastic Bag",
                "total_waste": 4.092,
                "ghg_reduction": 4.218851999999999,
                "proportion_percent": 0.06081862674186397
            },
            {
                "material_id": 150,
                "material_name": "Stretch Film",
                "total_waste": 3,
                "ghg_reduction": 3.093,
                "proportion_percent": 0.04458843602775951
            },
            {
                "material_id": 287,
                "material_name": "Screened color PET",
                "total_waste": 2,
                "ghg_reduction": 2.062,
                "proportion_percent": 0.029725624018506345
            },
            {
                "material_id": 4,
                "material_name": "PVC Pipes Green",
                "total_waste": 1,
                "ghg_reduction": 1.031,
                "proportion_percent": 0.014862812009253172
            },
            {
                "material_id": 260,
                "material_name": "Other Plastic LDPE",
                "total_waste": 1,
                "ghg_reduction": 1.031,
                "proportion_percent": 0.014862812009253172
            },
            {
                "material_id": 7,
                "material_name": "Breakable Plastic (PS)",
                "total_waste": 0,
                "ghg_reduction": 0,
                "proportion_percent": 0
            },
            {
                "material_id": 11,
                "material_name": "Boots",
                "total_waste": 0,
                "ghg_reduction": 0,
                "proportion_percent": 0
            }
        ],
        "Non-Specific General Waste": [
            {
                "material_id": 186,
                "material_name": "Waste to Landfill",
                "total_waste": 175,
                "ghg_reduction": 0,
                "proportion_percent": 2.6009921016193047
            }
        ],
        "Paper": [
            {
                "material_id": 129,
                "material_name": "Paper Cores",
                "total_waste": 154,
                "ghg_reduction": 873.796,
                "proportion_percent": 2.2888730494249883
            },
            {
                "material_id": 39,
                "material_name": "Brown Paper Box / Carton / Cardboard",
                "total_waste": 127,
                "ghg_reduction": 720.5980000000001,
                "proportion_percent": 1.8875771251751525
            },
            {
                "material_id": 46,
                "material_name": "Mixed Paper",
                "total_waste": 25,
                "ghg_reduction": 141.85000000000002,
                "proportion_percent": 0.37157030023132925
            },
            {
                "material_id": 223,
                "material_name": "Document Folder",
                "total_waste": 19,
                "ghg_reduction": 107.80600000000001,
                "proportion_percent": 0.2823934281758102
            }
        ],
        "Glass": [
            {
                "material_id": 23,
                "material_name": "LEO (12 bottle Carton)",
                "total_waste": 99.4182,
                "ghg_reduction": 27.4394232,
                "proportion_percent": 1.4776340168983335
            },
            {
                "material_id": 22,
                "material_name": "Colored Glass (Bottle)",
                "total_waste": 19,
                "ghg_reduction": 5.244000000000001,
                "proportion_percent": 0.2823934281758102
            }
        ],
        "Non-Specific Recyclables": [
            {
                "material_id": 298,
                "material_name": "Recyclables",
                "total_waste": 84.6,
                "ghg_reduction": 196.272,
                "proportion_percent": 1.2573938959828181
            }
        ],
        "Bulbs": [
            {
                "material_id": 105,
                "material_name": "Damaged bulb",
                "total_waste": 70,
                "ghg_reduction": 0,
                "proportion_percent": 1.040396840647722
            }
        ],
        "Chemicals and Liquids": [
            {
                "material_id": 206,
                "material_name": "Hazardous Chemicals",
                "total_waste": 43,
                "ghg_reduction": 0,
                "proportion_percent": 0.6391009163978864
            },
            {
                "material_id": 144,
                "material_name": "Contaminated containers",
                "total_waste": 42,
                "ghg_reduction": 0,
                "proportion_percent": 0.6242381043886333
            }
        ],
        "Electrical Wire": [
            {
                "material_id": 304,
                "material_name": "LAN Cable",
                "total_waste": 31,
                "ghg_reduction": 0,
                "proportion_percent": 0.4607471722868483
            }
        ],
        "Electrical Appliances": [
            {
                "material_id": 64,
                "material_name": "Computer accessories",
                "total_waste": 20,
                "ghg_reduction": 0,
                "proportion_percent": 0.2972562401850634
            }
        ],
        "Wood": [
            {
                "material_id": 286,
                "material_name": "Wood (General Waste)",
                "total_waste": 11,
                "ghg_reduction": 0,
                "proportion_percent": 0.16349093210178486
            }
        ],
        "Batteries": [
            {
                "material_id": 109,
                "material_name": "Old batteries",
                "total_waste": 1,
                "ghg_reduction": 0,
                "proportion_percent": 0.014862812009253172
            }
        ],
        "Personal Items": [
            {
                "material_id": 255,
                "material_name": "Antigen Test Kit (ATK)",
                "total_waste": 1,
                "ghg_reduction": 0,
                "proportion_percent": 0.014862812009253172
            }
        ]
    },
    "total_waste": 6728.2019
},
"diversion_data" : {
    "card_data": {
        "total_origin": 16,
        "complete_transfer": 0,
        "processing_transfer": 100,
        "completed_rate": 0
    },
    "sankey_data": [
        [
            "From",
            "To",
            "Weight"
        ],
        [
            "Chemicals and Liquids",
            "Composted by municipality",
            43
        ],
        [
            "Metal",
            "Composted by municipality",
            853
        ],
        [
            "Chemicals and Liquids",
            "Incineration with energy",
            42
        ],
        [
            "Paper",
            "Composted by municipality",
            154
        ],
        [
            "Food and Plant Waste",
            "Incineration with energy",
            744
        ],
        [
            "General Waste",
            "Composted by municipality",
            545
        ],
        [
            "Batteries",
            "Composted by municipality",
            1
        ],
        [
            "Paper",
            "Incineration with energy",
            160
        ],
        [
            "Metal",
            "Incineration with energy",
            12
        ],
        [
            "Food and Plant Waste",
            "Composted by municipality",
            20
        ],
        [
            "Electrical Appliances",
            "Incineration with energy",
            20
        ],
        [
            "Plastic",
            "Incineration with energy",
            445
        ],
        [
            "Plastic",
            "Composted by municipality",
            76
        ],
        [
            "Non-Specific General Waste",
            "Incineration with energy",
            175
        ],
        [
            "Concrete",
            "Incineration with energy",
            650
        ],
        [
            "Personal Items",
            "Incineration with energy",
            1
        ],
        [
            "Electrical Wire",
            "Composted by municipality",
            20
        ],
        [
            "Glass",
            "Composted by municipality",
            19
        ],
        [
            "Non-Specific Recyclables",
            "Incineration with energy",
            1
        ],
        [
            "Non-Specific Recyclables",
            "Composted by municipality",
            1
        ]
    ],
    "material_table": [
        {
            "key": 1,
            "materials": "Plastic",
            "data": [
                {
                    "month": "Jan",
                    "value": 68
                },
                {
                    "month": "Feb",
                    "value": 5
                },
                {
                    "month": "Mar",
                    "value": 391
                },
                {
                    "month": "May",
                    "value": 1
                },
                {
                    "month": "Jun",
                    "value": 50
                },
                {
                    "month": "Jul",
                    "value": 5
                },
                {
                    "month": "Aug",
                    "value": 13
                },
                {
                    "month": "Oct",
                    "value": 203
                },
                {
                    "month": "Nov",
                    "value": 883.1836999999999
                }
            ],
            "status": "Processing",
            "destination": [
                "Incineration with energy",
                "Composted by municipality"
            ]
        },
        {
            "key": 33,
            "materials": "Non-Specific Recyclables",
            "data": [
                {
                    "month": "Jun",
                    "value": 1
                },
                {
                    "month": "Jul",
                    "value": 12
                },
                {
                    "month": "Oct",
                    "value": 51
                },
                {
                    "month": "Nov",
                    "value": 20.6
                }
            ],
            "status": "Processing",
            "destination": [
                "Incineration with energy",
                "Composted by municipality"
            ]
        },
        {
            "key": 2,
            "materials": "Glass",
            "data": [
                {
                    "month": "Mar",
                    "value": 19
                },
                {
                    "month": "Nov",
                    "value": 99.4182
                }
            ],
            "status": "Processing",
            "destination": [
                "Composted by municipality"
            ]
        },
        {
            "key": 18,
            "materials": "Chemicals and Liquids",
            "data": [
                {
                    "month": "Jul",
                    "value": 43
                },
                {
                    "month": "Oct",
                    "value": 42
                }
            ],
            "status": "Processing",
            "destination": [
                "Incineration with energy",
                "Composted by municipality"
            ]
        },
        {
            "key": 5,
            "materials": "Metal",
            "data": [
                {
                    "month": "Feb",
                    "value": 1
                },
                {
                    "month": "Mar",
                    "value": 2
                },
                {
                    "month": "May",
                    "value": 800
                },
                {
                    "month": "Oct",
                    "value": 64
                }
            ],
            "status": "Processing",
            "destination": [
                "Incineration with energy",
                "Composted by municipality"
            ]
        },
        {
            "key": 10,
            "materials": "Food and Plant Waste",
            "data": [
                {
                    "month": "Feb",
                    "value": 450
                },
                {
                    "month": "Jul",
                    "value": 294
                },
                {
                    "month": "Aug",
                    "value": 20
                },
                {
                    "month": "Sep",
                    "value": 500
                },
                {
                    "month": "Oct",
                    "value": 50
                },
                {
                    "month": "Nov",
                    "value": 500
                }
            ],
            "status": "Processing",
            "destination": [
                "Incineration with energy",
                "Composted by municipality"
            ]
        },
        {
            "key": 23,
            "materials": "Bulbs",
            "data": [
                {
                    "month": "Sep",
                    "value": 70
                }
            ],
            "status": "Processing",
            "destination": []
        },
        {
            "key": 11,
            "materials": "General Waste",
            "data": [
                {
                    "month": "Apr",
                    "value": 500
                },
                {
                    "month": "May",
                    "value": 45
                },
                {
                    "month": "Oct",
                    "value": 11
                },
                {
                    "month": "Nov",
                    "value": 300
                }
            ],
            "status": "Processing",
            "destination": [
                "Composted by municipality"
            ]
        },
        {
            "key": 14,
            "materials": "Wood",
            "data": [
                {
                    "month": "Oct",
                    "value": 11
                }
            ],
            "status": "Processing",
            "destination": []
        },
        {
            "key": 9,
            "materials": "Electrical Wire",
            "data": [
                {
                    "month": "Aug",
                    "value": 20
                },
                {
                    "month": "Oct",
                    "value": 11
                }
            ],
            "status": "Processing",
            "destination": [
                "Composted by municipality"
            ]
        },
        {
            "key": 4,
            "materials": "Paper",
            "data": [
                {
                    "month": "Feb",
                    "value": 8
                },
                {
                    "month": "Jun",
                    "value": 127
                },
                {
                    "month": "Jul",
                    "value": 25
                },
                {
                    "month": "Sep",
                    "value": 154
                },
                {
                    "month": "Oct",
                    "value": 11
                }
            ],
            "status": "Processing",
            "destination": [
                "Incineration with energy",
                "Composted by municipality"
            ]
        },
        {
            "key": 13,
            "materials": "Batteries",
            "data": [
                {
                    "month": "Mar",
                    "value": 1
                }
            ],
            "status": "Processing",
            "destination": [
                "Composted by municipality"
            ]
        },
        {
            "key": 8,
            "materials": "Electrical Appliances",
            "data": [
                {
                    "month": "Mar",
                    "value": 20
                }
            ],
            "status": "Processing",
            "destination": [
                "Incineration with energy"
            ]
        },
        {
            "key": 28,
            "materials": "Non-Specific General Waste",
            "data": [
                {
                    "month": "Jun",
                    "value": 175
                }
            ],
            "status": "Processing",
            "destination": [
                "Incineration with energy"
            ]
        },
        {
            "key": 32,
            "materials": "Concrete",
            "data": [
                {
                    "month": "Jun",
                    "value": 650
                }
            ],
            "status": "Processing",
            "destination": [
                "Incineration with energy"
            ]
        },
        {
            "key": 17,
            "materials": "Personal Items",
            "data": [
                {
                    "month": "Oct",
                    "value": 1
                }
            ],
            "status": "Processing",
            "destination": [
                "Incineration with energy"
            ]
        }
    ]
}
}

PAGE_WIDTH_IN = 11.69
PAGE_HEIGHT_IN = 8.27
PRIMARY = colors.HexColor("#95c9c4")
TEXT = colors.HexColor("#5b6e8c")
CARD = colors.HexColor("#f6f8fb")
STROKE = colors.HexColor("#e6edf4")
BAR = colors.HexColor("#a9d5d0")
WHITE = colors.white
BLACK = colors.black
BAR2 = colors.HexColor("#77b9d8")
BAR3 = colors.HexColor("#c8ced4")
BAR4 = colors.HexColor("#8fcfc6")
SERIES_COLORS = [BAR, BAR2, BAR4, BAR3, TEXT]
def wrap_label(text, font, size, max_w):
    words = text.split()
    lines = []
    current = ""

    for w in words:
        test = f"{current} {w}".strip()
        if stringWidth(test, font, size) <= max_w:
            current = test
        else:
            if current:
                lines.append(current)
            current = w
    if current:
        lines.append(current)

    return lines

def _header(pdf, page_width_points: float, page_height_points: float, data: dict) -> None:
    text = data["users"]
    font_name = "Poppins-Regular"
    font_size = 12
    padding = 0.78 * inch  # whatever padding you want from right edge

    # 🧮 measure how wide the text is
    text_width = stringWidth(text, font_name, font_size)

    # 💡 calculate x-position = total width - text width - padding
    x = page_width_points - text_width - padding
    y = page_height_points - (0.7 * inch)  # your vertical position

    pdf.setFillColor(TEXT)
    pdf.setFont(font_name, font_size)
    pdf.drawString(x, y, text)

def _sub_header(pdf, page_width_points: float, page_height_points: float, data: dict, header_text: str) -> None:
    padding = 0.78 * inch
    location_data = data.get("location", [])
    if isinstance(location_data, list):
        location_text = ", ".join(map(str, location_data))
    else:
        location_text = str(location_data)
    
    pdf.setFillColor(PRIMARY)
    pdf.setFont("Poppins-Bold", 48)
    pdf.drawString(padding, page_height_points - (1.38 * inch), header_text)
    pdf.setFillColor(TEXT)
    pdf.setFont("Poppins-Regular", 12)
    pdf.drawString(padding, page_height_points - (1.75 * inch), f"Location: {location_text}")
    pdf.drawString(padding, page_height_points - (1.96 * inch), f"Date: {data['date_from']} - {data['date_to']}")


def _format_number(value) -> str:
    try:
        if isinstance(value, (int,)) or abs(value - int(value)) < 1e-9:
            return f"{value:,.0f}"
        return f"{value:,.2f}"
    except Exception:
        return str(value)

def _rounded_card(pdf, x, y, w, h, radius=8, fill=CARD, stroke=STROKE):
    pdf.setFillColor(fill)
    pdf.setStrokeColor(stroke)
    pdf.roundRect(x, y, w, h, radius, stroke=1, fill=1)

def _wrap_text_lines(pdf, text: str, max_width: float, font_name: str, font_size: float) -> list[str]:
    """
    Simple word-wrap: splits text into lines that fit within max_width for the given font.
    """
    pdf.setFont(font_name, font_size)
    words = (text or "").split()
    if not words:
        return []
    lines = []
    current = words[0]
    for word in words[1:]:
        trial = current + " " + word
        if stringWidth(trial, font_name, font_size) <= max_width:
            current = trial
        else:
            lines.append(current)
            current = word
    lines.append(current)
    return lines

def _stat_chip(pdf, x, y, w, h, title, value, variant="gray"):
    fill_color = WHITE if variant == "white" else CARD
    _rounded_card(pdf, x, y, w, h, radius=8, fill=fill_color)
    pad_x = 12 if variant == "white" else 20
    pdf.setFillColor(TEXT)
    pdf.setFont("Poppins-Regular", 8)
    pdf.drawString(x + pad_x, y + h - 18, title)
    pdf.setFont("Poppins-Regular", 12)
    pdf.drawString(x + pad_x, y + h - 32, _format_number(value))

def _progress_bar(pdf, x, y, w, h, ratio, bar_color=PRIMARY, back_color=STROKE):
    ratio = max(0.0, min(1.0, float(ratio or 0)))
    radius = h / 2

    # background
    pdf.setFillColor(back_color)
    pdf.roundRect(x, y, w, h, radius, stroke=0, fill=1)

    # foreground
    pdf.setFillColor(bar_color)
    bar_width = max(h, w * ratio)  # prevent ugly cut for small ratio
    pdf.roundRect(x, y, bar_width, h, radius, stroke=0, fill=1)


def _label_progress(pdf, x, y, w, label, value_text, ratio, bar_color, back_color, bar_h=8):
    pdf.setFillColor(TEXT)
    pdf.setFont("Poppins-Regular", 10)
    pdf.drawString(x, y + 16, label)
    pdf.setFillColor(TEXT)
    pdf.setFont("Poppins-Regular", 10)
    txt_w = stringWidth(value_text, "Poppins-Regular", 10)
    pdf.drawString(x + w - txt_w, y + 16, value_text)
    _progress_bar(pdf, x, y, w, bar_h, ratio, bar_color, back_color)

def _simple_bar_chart(pdf, x, y, w, h, chart_series):
    left_pad, bottom_pad, right_pad, top_pad = 32, 36, 24, 20
    gx = x + left_pad
    gy = y + bottom_pad
    gw = w - left_pad - right_pad
    gh = h - bottom_pad - top_pad

    # axes
    pdf.setStrokeColor(STROKE)
    pdf.line(gx, gy, gx, gy + gh)
    pdf.line(gx, gy, gx + gw, gy)

    # bars (grouped by month across all series)
    if not chart_series:
        return
    months = ["Jan","Feb","Mar","Apr","May","Jun","Jul","Aug","Sep","Oct","Nov","Dec"]
    # Determine up to 3 series (prefer most recent numeric years if possible)
    try:
        sorted_years = sorted([int(k) for k in chart_series.keys()])
        series_keys = [str(y) for y in sorted_years[-3:]]
    except Exception:
        # Fallback: preserve insertion order, take last 3
        series_keys = list(chart_series.keys())[-3:]
    values_by_series = {}
    for key in series_keys:
        arr = [0.0] * 12
        for pt in chart_series.get(key, []):
            m = str(pt.get("month", ""))
            if m in months:
                idx = months.index(m)
                try:
                    arr[idx] = float(pt.get("value", 0) or 0.0)
                except Exception:
                    arr[idx] = 0.0
        values_by_series[key] = arr

    vmax = 0.0
    for arr in values_by_series.values():
        vmax = max(vmax, max(arr) if arr else 0.0)
    if vmax <= 0:
        vmax = 1.0

    n_months = 12
    gap = 10
    slot_w = (gw - (n_months + 1) * gap) / max(1, n_months)
    group_scale = 0.86
    group_w = slot_w * group_scale
    s_count = max(1, len(series_keys))
    inner_gap_ratio = 0.06
    total_inner_gap = (s_count - 1) * group_w * inner_gap_ratio
    bar_w = (group_w - total_inner_gap) / s_count

    for mi in range(n_months):
        slot_x = gx + gap + mi * (slot_w + gap)
        group_x = slot_x + (slot_w - group_w) / 2
        for si, key in enumerate(series_keys):
            color = SERIES_COLORS[si % len(SERIES_COLORS)]
            pdf.setFillColor(color)
            v = values_by_series[key][mi]
            bh = (v / vmax) * (gh - 10)
            bx = group_x + si * (bar_w + group_w * inner_gap_ratio)
            pdf.rect(bx, gy, bar_w, bh, stroke=0, fill=1)
        # month label centered in slot
        lbl = months[mi]
        pdf.setFillColor(TEXT)
        pdf.setFont("Poppins-Regular", 8)
        lw = stringWidth(lbl, "Poppins-Regular", 8)
        pdf.drawString(slot_x + (slot_w - lw) / 2, gy - 14, lbl)

    # y-axis unit
    pdf.setFillColor(TEXT)
    pdf.setFont("Poppins-Regular", 9)
    pdf.drawString(gx - 18, gy + gh + 6, "kg")

    # legend for each series (years), right-aligned
    if series_keys:
        sq = 8
        cur_x = x + w - 10
        pdf.setFont("Poppins-Regular", 9)
        for si in reversed(range(len(series_keys))):
            label = str(series_keys[si])
            lw = stringWidth(label, "Poppins-Regular", 9)
            entry_w = sq + 6 + lw + 12
            cur_x -= entry_w
            pdf.setFillColor(SERIES_COLORS[si % len(SERIES_COLORS)])
            pdf.rect(cur_x, y + h - 18, sq, sq, stroke=0, fill=1)
            pdf.setFillColor(TEXT)
            pdf.drawString(cur_x + sq + 6, y + h - 18, label)

def _footer(pdf, page_width_points: float):
    text = "Copyright © 2018–2023 GEPP Sa-Ard Co., Ltd. ALL RIGHTS RESERVED"
    pdf.setFillColor(TEXT)
    pdf.setFont("Poppins-Regular", 9)
    tw = stringWidth(text, "Poppins-Regular", 9)
    pdf.drawString((page_width_points - tw) / 2, 0.25 * inch, text)

def _simple_pie_chart(pdf, x, y, size, values, colors_list, gap_width=2, gap_color=colors.white):
    # guard
    try:
        vals = [max(0.0, float(v or 0)) for v in values]
    except Exception:
        vals = [1.0]
    if not vals or sum(vals) <= 0:
        vals = [1.0]
    d = Drawing(size, size)
    pie = Pie()
    pie.x = 0
    pie.y = 0
    pie.width = size
    pie.height = size
    pie.data = vals
    pie.labels = None
    # remove outer border and add gaps between slices
    pie.strokeWidth = 0
    pie.slices.strokeWidth = max(0, int(gap_width))
    pie.slices.strokeColor = gap_color
    for i in range(len(vals)):
        pie.slices[i].fillColor = colors_list[i % len(colors_list)]
    d.add(pie)
    renderPDF.draw(d, pdf, x, y)

def draw_table(pdf, x, y, w, h, r=6, type="Header"):
    """
    Draw different styles of rectangles:
      - Header: rounded TOP corners only
      - Body:   normal sharp rectangle
      - Footer: rounded BOTTOM corners only
    """

    # Set border style
    pdf.setStrokeColor(colors.HexColor("#e2e8ef"))
    pdf.setLineWidth(0.5)

    # === BODY (normal rectangle) ==========================================
    if type == "Body":
        pdf.rect(x, y, w, h, stroke=1, fill=1)
        return

    p = pdf.beginPath()

    # === HEADER (rounded top only) ========================================
    if type == "Header":
        # bottom-left
        p.moveTo(x, y)
        # bottom-right
        p.lineTo(x + w, y)
        # right side up
        p.lineTo(x + w, y + h - r)
        # top-right corner
        p.arcTo(x + w - 2*r, y + h - 2*r, x + w, y + h, startAng=0, extent=90)
        # top edge
        p.lineTo(x + r, y + h)
        # top-left corner
        p.arcTo(x, y + h - 2*r, x + 2*r, y + h, startAng=90, extent=90)
        # left side down
        p.lineTo(x, y)

    # === FOOTER (rounded bottom only) =====================================
    elif type == "Footer":
        # start top-left
        p.moveTo(x, y + h)
        # top-right
        p.lineTo(x + w, y + h)
        # right side down
        p.lineTo(x + w, y + r)
        # bottom-right rounded
        p.arcTo(x + w - 2*r, y, x + w, y + 2*r, startAng=0, extent=-90)
        # bottom-left rounded
        p.lineTo(x + r, y)
        p.arcTo(x, y, x + 2*r, y + 2*r, startAng=-90, extent=-90)
        # left side up
        p.lineTo(x, y + h)

    pdf.drawPath(p, stroke=1, fill=1)

def draw_cover(pdf, page_width_points: float, page_height_points: float, data: dict) -> None:
    _header(pdf, page_width_points, page_height_points, data)
    middle = page_height_points / 2
    pdf.setFillColor(PRIMARY)  # set text color
    pdf.setFont("Poppins-Bold", 100) # set font and size
    pdf.drawString(0.63 * inch, middle + 20, "2025") 
    pdf.setFillColor(TEXT)
    pdf.setFont("Poppins-Regular", 38.5)
    pdf.drawString(0.63 * inch, middle - 20, "GEPP REPORT")
    pdf.setFont("Poppins-Regular", 16.5)
    pdf.drawString(0.63 * inch, middle - 40, "Data-Driven Transaformation")

    # 💡 Accent rectangle at the bottom
    pdf.setFillColor(PRIMARY)
    pdf.rect(4.54 * inch, middle - 45, page_width_points - (4.54 * inch), 2.07 * inch, fill=1, stroke=0)

def draw_overview(pdf, page_width_points: float, page_height_points: float, data: dict) -> None:
    pdf.showPage() # New page
    _header(pdf, page_width_points, page_height_points, data)
    _sub_header(pdf, page_width_points, page_height_points, data, "Overview")
    # layout measurements
    margin = 0.78 * inch
    content_top = page_height_points - (2.2 * inch)
    col_gap = 0.3 * inch
    left_col_w = 3.7 * inch
    right_col_w = page_width_points - margin - margin - left_col_w - col_gap

    # small stat chips (top-left row)
    chip_w = 1.78 * inch
    chip_h = 0.60 * inch
    chip_y = content_top - chip_h
    _stat_chip(pdf, margin, chip_y, chip_w, chip_h, "Total Transactions", data["overview_data"]["transactions_total"])
    _stat_chip(pdf, margin + chip_w + 12, chip_y, chip_w, chip_h, "Total Approved", data["overview_data"]["transactions_approved"])

    # left column cards
    # Key Indicators
    ki_h = 2.2 * inch
    ki_y = chip_y - 16 - ki_h
    _rounded_card(pdf, margin, ki_y, left_col_w, ki_h, radius=8)
    pad = 20
    pdf.setFillColor(TEXT)
    pdf.setFont("Poppins-Medium", 12)
    pdf.drawString(margin + pad, page_height_points - (3.42 * inch), "Key Indicators")

    ki = data["overview_data"]["key_indicators"]
    tw = float(ki.get("total_waste", 0) or 0)
    rr = float(ki.get("recycle_rate", 0) or 0)
    ghg = float(ki.get("ghg_reduction", 0) or 0)
    # normalize non-percentage bars against max of tw & ghg
    norm_base = max(tw, ghg, 1.0)
    row_w = left_col_w - 2 * pad
    row_x = margin + pad
    row_y = ki_y + ki_h - 50
    _label_progress(pdf, row_x, row_y - 24, row_w, "Total Waste (kg)", _format_number(tw), tw / norm_base, colors.HexColor("#b7c6cc"), colors.HexColor("#e1e7ef"), bar_h=6)
    _label_progress(pdf, row_x, row_y - 58, row_w, "Recycle rate (%)", f"{rr:,.2f}", rr / 100.0, colors.HexColor("#8fcfc6"), colors.HexColor("#e1e7ef"), bar_h=6)
    _label_progress(pdf, row_x, row_y - 92, row_w, "GHG Reduction (kgCO2e)", _format_number(ghg), ghg / norm_base, colors.HexColor("#77b9d8"), colors.HexColor("#e1e7ef"), bar_h=6)

    # Top Recyclables
    tr_h = 2.15 * inch
    tr_y = ki_y - 18 - tr_h
    _rounded_card(pdf, margin, tr_y, left_col_w, tr_h, radius=8)

    pdf.setFillColor(TEXT)
    pdf.setFont("Poppins-Medium", 12)
    pdf.drawString(margin + pad, tr_y + tr_h - 30, "Top Recyclables")
    items = data["overview_data"].get("top_recyclables", [])[:3]
    if items:
        max_val = max(float(it.get("total_waste", 0) or 0) for it in items) or 1.0
        y_ptr = tr_y + tr_h - 72
        for it in items:
            name = str(it.get("origin_name", ""))
            val = float(it.get("total_waste", 0) or 0)
            ratio = val / max_val
            _label_progress(pdf, margin + pad, y_ptr, left_col_w - 2 * pad, name, _format_number(val), ratio, colors.HexColor("#c8ced4"), colors.HexColor("#e1e7ef"), bar_h=6)
            y_ptr -= 32

    # Right column: Overall card with small stats and chart
    overall_x = margin + left_col_w + col_gap
    overall_y = tr_y
    overall_h = (chip_y - overall_y) + chip_h  # span to top row baseline
    _rounded_card(pdf, overall_x, overall_y, right_col_w, overall_h, radius=8, fill=WHITE)
    pdf.setFillColor(TEXT)
    pdf.setFont("Poppins-Medium", 12)
    pdf.drawString(overall_x + 16, overall_y + overall_h - 30, "Overall")

    # top stat chips in overall card
    stats = data["overview_data"]["overall_charts"]["chart_stat_data"]
    sw = 1.78 * inch
    sh = 0.60 * inch
    sy = overall_y + overall_h - 26 - 16 - sh
    for i, st in enumerate(stats[:3]):
        sx = overall_x + 16 + i * (sw + 8)
        _stat_chip(pdf, sx, sy, sw, sh, st["title"], st["value"], "white")

    # bar chart (supports multiple years)
    chart_data = data["overview_data"]["overall_charts"]["chart_data"]
    cy = overall_y + 16
    ch = (sy - cy - 16) * 0.85  # slightly shorter chart height
    _simple_bar_chart(pdf, overall_x + 12, cy, right_col_w - 24, ch, chart_data)

    _footer(pdf, page_width_points)

def draw_performance(pdf, page_width_points: float, page_height_points: float, data: dict, performance_data: dict) -> None:
    pdf.showPage() # New page
    _header(pdf, page_width_points, page_height_points, data)
    _sub_header(pdf, page_width_points, page_height_points, data, "Performance")
    margin = 0.78 * inch

    _rounded_card(pdf, margin, page_height_points - (6.98 * inch), 3.22 * inch, 4.54* inch, radius=8, fill=WHITE)
    pdf.setFillColor(TEXT)
    pdf.setFont("Poppins-Medium", 12)
    pdf.drawString(1 * inch, page_height_points - (2.85 * inch), f"{performance_data['branchName']}")
    pdf.setFont("Poppins-Regular", 8)
    label_text = "Recycling Rate"
    label_width = stringWidth(label_text, "Poppins-Medium", 8)
    pdf.drawString(3.82 * inch - label_width, page_height_points - (2.72 * inch), label_text)
    pdf.setFont("Poppins-Bold", 13)
    value_text = f"{performance_data['recyclingRatePercent']} %"
    value_width = stringWidth(value_text, "Poppins-Medium", 13)
    pdf.drawString(3.82 * inch - value_width, page_height_points - (2.97 * inch), value_text)
    
    for idx, (label, amount) in enumerate(performance_data["metrics"].items()):
        start_y = page_height_points - (3.41 * inch)
        bar_h = 0.08 * inch
        gap = 0.36 * inch
        y = start_y - idx * (bar_h + gap)
        pdf.setFillColor(TEXT)
        pdf.setFont("Poppins-Regular", 8)
        pdf.drawString(1 * inch, y + bar_h + 0.12 * inch, label)
        value_text = f"{amount} kg"
        value_width = stringWidth(value_text, "Poppins-Regular", 8)
        pdf.drawString(1 * inch + 2.8 * inch - value_width, y + bar_h + 0.12 * inch, value_text)
        _progress_bar(pdf, 1 * inch, y, 2.8 * inch, bar_h, amount / performance_data["totalWasteKg"], MATERIAL_COLORS[label])
    gap = 1 * inch
    outer_x = gap + 3.22 * inch
    outer_y = page_height_points - (6.98 * inch)
    outer_w = 6.8 * inch
    outer_h = 4.54 * inch
    _rounded_card(pdf, outer_x, outer_y, outer_w, outer_h, radius=8, fill=colors.HexColor("#f1f5f9"))
    # inner card with 24px padding and white fill
    pad = 16  # points
    inner_x = outer_x + pad
    inner_y = outer_y + pad
    inner_w = outer_w - 2 * pad
    inner_h = outer_h - 2 * pad
    _rounded_card(pdf, inner_x, inner_y, inner_w, inner_h, radius=8, fill=WHITE)
    pdf.setFillColor(TEXT)
    pdf.setFont("Poppins-Medium", 12)
    # place title at top-left of inner card with 16pt padding
    pdf.drawString(inner_x + 16, inner_y + inner_h - 16 - 12, "All Building")
    pdf.setFont("Poppins-Regular", 10)
    for idx, building in enumerate(performance_data["buildings"]):
        y = inner_y + inner_h - 0.85 * inch - idx * (0.55 * inch)
        pdf.setFillColor(TEXT)
        pdf.drawString(inner_x + 16, y, building["buildingName"])
        value_text = f"{building['totalWasteKg']} kg"
        value_width = stringWidth(value_text, "Poppins-Regular", 8)
        pdf.drawString(inner_x + 4 * inch - value_width, y, value_text)
        _progress_bar(pdf, inner_x + 16, y - 0.2 * inch, inner_x - 0.5 * inch, 0.08 * inch, building['totalWasteKg'] / performance_data["totalWasteKg"], colors.HexColor("#b7cbd6"))
    # Implement pie chart here
    pdf.setFillColor(TEXT)
    pdf.setFont("Poppins-Regular", 10)
    pie_size = 1.20 * inch
    pie_x = inner_x + inner_w - pie_size - 16

    # 1) Total Buildings
    title1_y = inner_y + inner_h - 48
    pdf.drawString(pie_x, title1_y, "Total Buildings")
    buildings_values = [float(b.get("totalWasteKg", 0) or 0) for b in performance_data.get("buildings", [])]
    mono_color = colors.HexColor("#b7cbd6")
    mono_colors_list = [mono_color for _ in buildings_values] or [mono_color]
    _simple_pie_chart(pdf, pie_x, title1_y - 8 - pie_size, pie_size, buildings_values, mono_colors_list, gap_width=1, gap_color=colors.white)

    # 2) All Types of Waste
    title2_y = title1_y - pie_size - 32
    pdf.drawString(pie_x, title2_y, "All Types of Waste")
    metrics_items = list(performance_data.get("metrics", {}).items())
    waste_values = [float(v or 0) for _, v in metrics_items]
    waste_colors = [MATERIAL_COLORS.get(lbl, BAR3) for lbl, _ in metrics_items]
    if not waste_colors:
        waste_colors = SERIES_COLORS
    _simple_pie_chart(pdf, pie_x, title2_y - 8 - pie_size, pie_size, waste_values, waste_colors, gap_width=1, gap_color=colors.white)
    _footer(pdf, page_width_points)

def draw_performance_table(pdf, page_width_points: float, page_height_points: float, data: dict) -> None:
    padding = 0.78 * inch
    branches_per_page = 7
    total_branches = len(data["performance_data"])
    icon_path = "scripts/BranchIcon.png"  # path to your icon
    icon_size = 10  # width & height in points

    # Draw the icon before branch name
    for page_idx in range(0, total_branches, branches_per_page):
        pdf.showPage()  # New page
        _header(pdf, page_width_points, page_height_points, data)
        _sub_header(pdf, page_width_points, page_height_points, data, "Performance")

        pdf.setFillColor(TEXT)
        pdf.setFont("Poppins-Medium", 12)
        pdf.drawString(padding, page_height_points - (2.5 * inch), "Detailed Performance Metrics")

            # Draw table header
        pdf.setFillColor(colors.HexColor("#f1f5f9"))
        draw_table(pdf, padding, page_height_points - (3 * inch), page_width_points - 2 * padding, 24, 8, "Header")
        pdf.setFillColor(TEXT)
        pdf.setFont("Poppins-Regular", 8)
        pdf.drawString(padding + 16, page_height_points - (2.88 * inch), "Building Name")
        pdf.drawString(padding + 1.8 * inch, page_height_points - (2.88 * inch), "Total Waste (kg)")
        pdf.drawString(padding + 3.2 * inch, page_height_points - (2.88 * inch), "General (kg)")
        pdf.drawString(padding + 4.4 * inch, page_height_points - (2.88 * inch), "Total Recyclable incl. Recycled Organic Waste (kg)")
        pdf.drawString(padding + 7.7 * inch, page_height_points - (2.88 * inch), "Recycling Rate (%)")
        pdf.drawString(padding + 9.3 * inch, page_height_points - (2.88 * inch), "Status")

            # Draw rows for this page
        page_branches = data["performance_data"][page_idx:page_idx + branches_per_page]
        for idx, branch in enumerate(page_branches):
            y_base = page_height_points - (3 * inch) - 32 - (idx * 32)

            # Use 'Footer' if last row on page, else 'Body'
            table_type = "Footer" if idx == len(page_branches) - 1 else "Body"
            pdf.setFillColor(WHITE)
            draw_table(pdf, padding, y_base, page_width_points - 2 * padding, 32, 8, table_type)

            pdf.setFillColor(TEXT)
            pdf.setFont("Poppins-Regular", 8)
            y_text = y_base + 12  # Align text in table row
            pdf.drawImage(icon_path, padding + 16, y_base + 11, width=icon_size, height=icon_size, mask='auto')
            pdf.drawString(padding + 30, y_base + 12, branch["branchName"])
            pdf.drawString(padding + 1.8 * inch, y_text, _format_number(branch["totalWasteKg"]))
            pdf.drawString(padding + 3.2 * inch, y_text, _format_number(branch["metrics"]["General Waste"]))
            pdf.drawString(padding + 4.4 * inch, y_text, _format_number(branch["metrics"]["Recyclable Waste"] + branch["metrics"]["Organic Waste"]))
            pdf.drawString(padding + 7.7 * inch, y_text, f"{branch['recyclingRatePercent']} %")

            # Circle + Status
            color = colors.HexColor("#0bb980") if branch["recyclingRatePercent"] > 20 else colors.HexColor("#f49d0d")
            pdf.setFillColor(color)
            circle_radius = 3.5
            circle_x = padding + 9.2 * inch
            pdf.circle(circle_x, y_text + 3, circle_radius, stroke=0, fill=1)

            pdf.drawString(padding + 9.3 * inch, y_text, "Normal" if branch["recyclingRatePercent"] > 20 else "Need Imprv")

def draw_comparison_advice(pdf, page_width_points: float, page_height_points: float, data: dict) -> None:
    pdf.showPage()  # New page
    _header(pdf, page_width_points, page_height_points, data)
    _sub_header(pdf, page_width_points, page_height_points, data, "Comparison")
    
    # ================== Layout ==================
    margin = 0.78 * inch
    gap = 0.3 * inch
    card_w = (page_width_points - 2 * margin - 2 * gap) / 3.0
    card_h = 5 * inch
    content_top = page_height_points - 2.2 * inch
    card_y = content_top - card_h
    
    # Card positions and data mapping
    cards = [
        {"x": margin, "title": "Opportunities", "data": data["comparison_data"]["scores"].get("opportunities", [])},
        {"x": margin + card_w + gap, "title": "Quick Wins", "data": data["comparison_data"]["scores"].get("quickwins", [])},
        {"x": margin + 2 * (card_w + gap), "title": "Risks", "data": data["comparison_data"]["scores"].get("risks", [])}
    ]
    
    # ================== Draw Cards ==================
    for card in cards:
        _rounded_card(pdf, card["x"], card_y, card_w, card_h, radius=8, fill=WHITE)
        # Title
        pdf.setFillColor(TEXT)
        pdf.setFont("Poppins-Medium", 12)
        pdf.drawString(card["x"] + 16, card_y + card_h - 24, card["title"])
    
    # ================== Draw Recommendations ==================
    body_font = "Poppins-Regular"
    body_size = 8
    leading = 12
    pad = 16
    paragraph_gap = 8
    label_font = "Poppins-Medium"
    label_size = 9

    def _draw_recommendations(items, x_left):
        y_cursor = card_y + card_h - 40  # start below title
        max_w = card_w - 2 * pad
        pdf.setFillColor(TEXT)
        pdf.setFont(body_font, body_size)
        for itm in items[:2]:  # only first 2 recommendations
            rec = str(itm.get("recommendation", "")).strip()
            if not rec:
                continue
            # Compose single-paragraph: "<Header>: Recommendation"
            crit_name = str(itm.get("criteria_name") or itm.get("condition_name") or itm.get("name") or "").strip()
            display_name = crit_name.replace("_", " ") if crit_name else ""
            para_text = f"{display_name}: {rec}" if display_name else rec
            # No bullet; render as plain paragraph with header prefix
            text_x_offset = 0
            usable_w = max_w
            # Wrap paragraph text within usable width
            pdf.setFont(body_font, body_size)
            lines = _wrap_text_lines(pdf, para_text, usable_w, body_font, body_size)
            if not lines:
                continue
            # Draw first line (header in medium weight)
            if y_cursor < (card_y + pad):
                return
            first_line_x = x_left + pad + text_x_offset
            header_prefix = f"{display_name}: " if display_name else ""
            if header_prefix and lines[0].startswith(header_prefix):
                # draw header in medium
                pdf.setFont(label_font, label_size)
                pdf.drawString(first_line_x, y_cursor, header_prefix)
                header_w = stringWidth(header_prefix, label_font, label_size)
                # draw remainder in regular
                remainder = lines[0][len(header_prefix):]
                if remainder:
                    pdf.setFont(body_font, body_size)
                    pdf.drawString(first_line_x + header_w, y_cursor, remainder)
            else:
                # no header or did not fit as prefix
                pdf.setFont(body_font, body_size)
                pdf.drawString(first_line_x, y_cursor, lines[0])
            y_cursor -= leading
            # Draw remaining wrapped lines (indented, without bullet)
            for line in lines[1:]:
                if y_cursor < (card_y + pad):
                    return  # stop if out of space
                pdf.drawString(x_left + pad + text_x_offset, y_cursor, line)
                y_cursor -= leading
            # Extra space between recommendations
            y_cursor -= paragraph_gap
            if y_cursor < (card_y + pad):
                return

    # Loop through cards and draw recommendations
    for card in cards:
        _draw_recommendations(card["data"], card["x"])
    
    # ================== Footer ==================
    _footer(pdf, page_width_points)

def draw_comparison(pdf, page_width_points: float, page_height_points: float, data: dict) -> None:
    padding = 0.78 * inch
    pdf.showPage()  # New page
    _header(pdf, page_width_points, page_height_points, data)
    _sub_header(pdf, page_width_points, page_height_points, data, "Comparison")
    # Card
    card_x = padding
    card_y = 0.75 * inch
    card_w = page_width_points - 2 * padding
    card_h = 5.2 * inch
    _rounded_card(pdf, card_x, card_y, card_w, card_h, radius=8, fill=WHITE)

    # Layout
    pad = 20
    legend_w = 3.0 * inch
    bars_w = card_w - 2 * pad - legend_w
    bars_center_x = card_x + pad + (bars_w / 2.0)
    top_y = card_y + card_h - 48
    bottom_y = card_y + 28

    # Data
    left_mat = (data.get("comparison_data", {}).get("left", {}) or {}).get("material", {}) or {}
    right_mat = (data.get("comparison_data", {}).get("right", {}) or {}).get("material", {}) or {}
    left_period = str((data.get("comparison_data", {}).get("left", {}) or {}).get("period", ""))
    right_period = str((data.get("comparison_data", {}).get("right", {}) or {}).get("period", ""))
    categories = [
        "Organic Waste",
        "Recyclable Waste",
        "Construction Waste",
        "General Waste",
        "Electronic Waste",
        "Hazardous Waste",
        "Waste To Energy",
        "Bio-Hazardous Waste",
    ]

    def get_val(d, k):
        try:
            return float(d.get(k, 0) or 0)
        except Exception:
            return 0.0

    max_val = max(
        [1.0]
        + [get_val(left_mat, c) for c in categories]
        + [get_val(right_mat, c) for c in categories]
    )
    half_w = (bars_w / 2.0) - 6
    bar_h = 26
    row_gap = 40
    # smaller cap radius to reduce roundness at outer ends
    cap_r = min(bar_h * 0.35, bar_h / 2.0)

    # Center line and year labels
    pdf.setStrokeColor(STROKE)
    pdf.setLineWidth(1)
    pdf.line(bars_center_x, bottom_y, bars_center_x, top_y + 8)
    pdf.setFillColor(TEXT)
    pdf.setFont("Poppins-Medium", 14)
    lpw = stringWidth(left_period, "Poppins-Medium", 14)
    pdf.drawString(bars_center_x - 8 - lpw, top_y + 20, left_period)   # right-aligned to center - 8
    pdf.drawString(bars_center_x + 8, top_y + 20, right_period)        # left-aligned to center + 8

    # Colors
    left_color = colors.HexColor("#d3dbe3")
    right_color = colors.HexColor("#c9e7df")

    # Helpers to draw bars with rounded end only
    def draw_right_bar(center_x, y_mid, length, height, color):
        if length <= 0:
            return 0.0
        r = min(cap_r, height / 2.0, length)
        rect_len = max(0.0, length - r)  # flat part before rounded end
        left = center_x
        right = center_x + length
        bottom = y_mid - height / 2.0
        top = y_mid + height / 2.0
        p = pdf.beginPath()
        p.moveTo(left, bottom)
        p.lineTo(right - r, bottom)
        # bottom-right corner (from bottom edge to right edge, clockwise)
        p.arcTo(right - 2 * r, bottom, right, bottom + 2 * r, startAng=270, extent=90)
        # right edge up
        p.lineTo(right, top - r)
        # top-right corner (from right edge to top edge, counter-clockwise)
        p.arcTo(right - 2 * r, top - 2 * r, right, top, startAng=0, extent=90)
        # top edge back to center
        p.lineTo(left, top)
        # left edge down (square inner end)
        p.lineTo(left, bottom)
        pdf.setFillColor(color)
        pdf.drawPath(p, stroke=0, fill=1)
        return rect_len

    def draw_left_bar(center_x, y_mid, length, height, color):
        if length <= 0:
            return 0.0
        r = min(cap_r, height / 2.0, length)
        rect_len = max(0.0, length - r)  # flat part before rounded end
        right = center_x
        left = center_x - length
        bottom = y_mid - height / 2.0
        top = y_mid + height / 2.0
        p = pdf.beginPath()
        p.moveTo(right, bottom)
        p.lineTo(left + r, bottom)
        # bottom-left corner (from bottom edge to left edge, counter-clockwise)
        p.arcTo(left, bottom, left + 2 * r, bottom + 2 * r, startAng=270, extent=-90)
        # left edge up
        p.lineTo(left, top - r)
        # top-left corner (from left edge to top edge, clockwise)
        p.arcTo(left, top - 2 * r, left + 2 * r, top, startAng=180, extent=-90)
        # top edge back to center
        p.lineTo(right, top)
        # right edge down (square inner end)
        p.lineTo(right, bottom)
        pdf.setFillColor(color)
        pdf.drawPath(p, stroke=0, fill=1)
        return rect_len

    # Bars
    pdf.setFont("Poppins-Medium", 11)
    for idx, cat in enumerate(categories):
        y = top_y - idx * row_gap
        left_v = get_val(left_mat, cat)
        right_v = get_val(right_mat, cat)
        left_len = max(0.0, min(half_w, (left_v / max_val) * half_w))
        right_len = max(0.0, min(half_w, (right_v / max_val) * half_w))

        # left bar (2024)
        left_rect = draw_left_bar(bars_center_x, y, left_len, bar_h, left_color)
        # right bar (2025)
        right_rect = draw_right_bar(bars_center_x, y, right_len, bar_h, right_color)

        # values inside bars
        txt_left = _format_number(left_v)
        txt_right = _format_number(right_v)
        pdf.setFillColor(TEXT)
        # left value: try inside flat part; else place just left of bar
        sw_left = stringWidth(txt_left, "Poppins-Medium", 11)
        avail_left = max(0.0, left_rect - 16)  # 8px padding on each side
        if left_rect > 0 and sw_left <= avail_left:
            x_text = bars_center_x - left_rect + 8  # start at flat part + padding
            pdf.drawString(x_text, y - 4, txt_left)
        else:
            x_out = max(card_x + 6, bars_center_x - left_len - sw_left - 8)
            pdf.drawString(x_out, y - 4, txt_left)

        # right value: try inside flat part; else place just right of bar (avoid legend overlap)
        sw_right = stringWidth(txt_right, "Poppins-Medium", 11)
        avail_right = max(0.0, right_rect - 16)  # 8px padding on each side
        if right_rect > 0 and sw_right <= avail_right:
            x_text = bars_center_x + right_rect - sw_right - 8  # end before rounded cap
            pdf.drawString(x_text, y - 4, txt_right)
        else:
            x_out_candidate = bars_center_x + right_len + 8
            x_max = (card_x + card_w - legend_w + 8) - sw_right - 4  # keep clear of legend
            x_out = min(x_out_candidate, x_max)
            pdf.drawString(max(bars_center_x + 4, x_out), y - 4, txt_right)

    # Right legend with deltas
    legend_x = card_x + card_w - legend_w + 8
    y_legend = top_y
    pdf.setFillColor(TEXT)
    for idx, cat in enumerate(categories):
        y = y_legend - idx * row_gap
        # category name
        pdf.setFont("Poppins-Medium", 12)
        display_name = cat.replace(" Waste", "")
        display_name = display_name.replace("Bio-Hazardous", "Bio-Hazardous")
        pdf.drawString(legend_x, y + 8, display_name if display_name != "Waste To Energy" else "Waste To Energy")

        # delta
        lval = get_val(left_mat, cat)
        rval = get_val(right_mat, cat)
        delta = rval - lval
        sign = "+" if delta >= 0 else "-"
        abs_delta = abs(delta)
        if abs(abs_delta - round(abs_delta)) < 1e-6:
            delta_str = f"{int(round(abs_delta))}"
        else:
            delta_str = f"{abs_delta:,.1f}"
        pdf.setFont("Poppins-Regular", 11)
        pdf.drawString(legend_x, y - 8, f"{sign} {delta_str} kg.")
    
    _footer(pdf, page_width_points)

    pdf.showPage()  # New page
    _header(pdf, page_width_points, page_height_points, data)
    _sub_header(pdf, page_width_points, page_height_points, data, "Comparison")
    # two stacked full-width cards (stretched within padding), chart on top, empty below
    margin = padding
    gap = 0.3 * inch
    card_w2 = (page_width_points - 2 * margin)
    card_h2 = 2.5 * inch
    # define a safe content area to avoid header/footer overlap and center the stack
    content_bottom = 0.8 * inch
    content_top = page_height_points - 3.0 * inch
    stack_h = (2 * card_h2) + gap
    available_h = max(0.0, content_top - content_bottom)
    start_y = content_bottom + max(0.0, (available_h - stack_h) / 2.0)
    lower_card_y = start_y
    upper_card_y = lower_card_y + card_h2 + gap
    # chart card on top
    card_y2 = upper_card_y
    x_left = margin
    _rounded_card(pdf, x_left, card_y2, card_w2, card_h2, radius=8, fill=WHITE)
    # empty box stacked below the chart card
    _rounded_card(pdf, x_left, lower_card_y, card_w2, card_h2, radius=8, fill=WHITE)
    # --------- Left card: Quantity Comparison (auto month range) ----------
    # Data
    left_months = (data.get("comparison_data", {}).get("left", {}) or {}).get("month", {}) or {}
    right_months = (data.get("comparison_data", {}).get("right", {}) or {}).get("month", {}) or {}
    series_a_label = (data.get("comparison_data", {}).get("left", {}) or {}).get("period", "") or "Left"
    series_b_label = (data.get("comparison_data", {}).get("right", {}) or {}).get("period", "") or "Right"

    # Month ordering helper (supports "Jan"/"January"/1..12)
    _months_short = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
    _map_idx = {m.lower(): i for i, m in enumerate(_months_short)}
    _map_idx.update({
        "january": 0, "february": 1, "march": 2, "april": 3, "may": 4, "june": 5,
        "july": 6, "august": 7, "september": 8, "october": 9, "november": 10, "december": 11
    })
    def _month_index(k):
        s = str(k).strip()
        lower = s.lower()
        if lower in _map_idx:
            return _map_idx[lower]
        try:
            n = int(s)
            if 1 <= n <= 12:
                return n - 1
        except Exception:
            pass
        return 99  # unknown goes last
    def _month_label(k):
        idx = _month_index(k)
        return _months_short[idx] if 0 <= idx < 12 else str(k)

    # Determine month sequence from union of keys
    month_keys = sorted(set(list(left_months.keys()) + list(right_months.keys())), key=_month_index)

    # Layout inside left card
    pad2 = 16
    title_y2 = card_y2 + card_h2 - 20
    chart_left2 = x_left + 44
    chart_right2 = x_left + card_w2 - pad2
    chart_bottom2 = card_y2 + 24
    chart_top2 = card_y2 + card_h2 - 36
    chart_w2 = max(1.0, chart_right2 - chart_left2)
    chart_h2 = max(1.0, chart_top2 - chart_bottom2)

    # Title
    pdf.setFillColor(TEXT)
    pdf.setFont("Poppins-Medium", 12)
    pdf.drawString(x_left + pad2, title_y2, "Quantity Comparison")

    # Legend (top-right)
    sw2 = 10
    sh2 = 6
    s1w2 = stringWidth(series_a_label, "Poppins-Regular", 9)
    s2w2 = stringWidth(series_b_label, "Poppins-Regular", 9)
    total_legend_w2 = sw2 + 6 + s1w2 + 14 + sw2 + 6 + s2w2
    lx2 = chart_right2 - pad2 - total_legend_w2 + pad2
    ly2 = title_y2 + 1
    pdf.setFillColor(BAR)
    pdf.roundRect(lx2, ly2, sw2, sh2, 3, stroke=0, fill=1)
    pdf.setFillColor(TEXT)
    pdf.setFont("Poppins-Regular", 9)
    pdf.drawString(lx2 + sw2 + 6, ly2 - 1, series_a_label)
    lx2b = lx2 + sw2 + 6 + s1w2 + 14
    pdf.setFillColor(BAR2)
    pdf.roundRect(lx2b, ly2, sw2, sh2, 3, stroke=0, fill=1)
    pdf.setFillColor(TEXT)
    pdf.drawString(lx2b + sw2 + 6, ly2 - 1, series_b_label)

    # Axes and grid
    max_val2 = 1.0
    for mk in month_keys:
        lv = float(left_months.get(mk, 0) or 0)
        rv = float(right_months.get(mk, 0) or 0)
        if lv > max_val2:
            max_val2 = lv
        if rv > max_val2:
            max_val2 = rv
    # choose a nice top for ticks
    mag2 = 1.0
    while mag2 * 10 <= max_val2:
        mag2 *= 10.0
    for mul in (1.0, 2.0, 2.5, 5.0, 10.0):
        top_val2 = mul * mag2
        if top_val2 >= max_val2:
            break
    ticks2 = [0.0, top_val2 / 2.0, top_val2]
    pdf.setStrokeColor(STROKE)
    pdf.setLineWidth(0.5)
    for tv in ticks2:
        y = chart_bottom2 + (tv / top_val2) * chart_h2
        pdf.line(chart_left2, y, chart_right2, y)
        # y-axis tick labels
        lbl = _format_number(round(tv))
        lw = stringWidth(lbl, "Poppins-Regular", 8)
        pdf.setFillColor(TEXT)
        pdf.setFont("Poppins-Regular", 8)
        pdf.drawString(chart_left2 - 6 - lw, y - 3, lbl)
    # y-axis label "Kg."
    pdf.saveState()
    pdf.setFillColor(TEXT)
    pdf.setFont("Poppins-Regular", 9)
    pdf.translate(x_left + 12, (chart_bottom2 + chart_top2) / 2.0)
    pdf.rotate(90)
    pdf.drawCentredString(0, 0, "Kg.")
    pdf.restoreState()

    # Helper: draw rectangle rounded only at the top corners with smaller radius
    def _draw_top_round_rect(x, y, w, h, r, color):
        if w <= 0 or h <= 0:
            return
        rr = max(0.0, min(r, w / 2.0, h))
        pth = pdf.beginPath()
        # bottom-left to bottom-right (flat bottom)
        pth.moveTo(x, y)
        pth.lineTo(x + w, y)
        # right edge up to start of top-right arc
        pth.lineTo(x + w, y + h - rr)
        # top-right corner
        pth.arcTo(x + w - 2 * rr, y + h - 2 * rr, x + w, y + h, startAng=0, extent=90)
        # top edge to start of top-left arc
        pth.lineTo(x + rr, y + h)
        # top-left corner
        pth.arcTo(x, y + h - 2 * rr, x + 2 * rr, y + h, startAng=90, extent=90)
        # left edge down to bottom-left
        pth.lineTo(x, y)
        pdf.setFillColor(color)
        pdf.drawPath(pth, stroke=0, fill=1)

    # Bars
    groups2 = max(1, len(month_keys))
    # adaptive gaps and widths to fit variable month ranges
    group_gap2 = min(22, max(8, chart_w2 / max(3.0, groups2 * 4.0)))
    group_w2 = max(1.0, (chart_w2 - (groups2 - 1) * group_gap2) / groups2)
    bar_gap2 = min(10, max(5, group_w2 * 0.18))
    bar_w2 = max(5, min(24, (group_w2 - bar_gap2) / 2.0))
    for i, mk in enumerate(month_keys):
        gx = chart_left2 + i * (group_w2 + group_gap2)
        inner_offset2 = (group_w2 - (2 * bar_w2 + bar_gap2)) / 2.0
        # left series
        lv = float(left_months.get(mk, 0) or 0)
        lh = (lv / top_val2) * chart_h2
        _draw_top_round_rect(gx + inner_offset2, chart_bottom2, bar_w2, lh, min(bar_w2 * 0.25, 5), BAR)
        # right series
        rv = float(right_months.get(mk, 0) or 0)
        rh = (rv / top_val2) * chart_h2
        _draw_top_round_rect(gx + inner_offset2 + bar_w2 + bar_gap2, chart_bottom2, bar_w2, rh, min(bar_w2 * 0.25, 5), BAR2)
        # month label
        mlabel = _month_label(mk)
        pdf.setFillColor(TEXT)
        pdf.setFont("Poppins-Regular", 9)
        mw2 = stringWidth(mlabel, "Poppins-Regular", 9)
        pdf.drawString(gx + (group_w2 - mw2) / 2.0, card_y2 + 8, mlabel)
    # --------- Lower card: Dynamic month table (header + 3 rows) ----------
    pdf.setFillColor(TEXT)
    pdf.setFont("Poppins-Medium", 12)
    pdf.drawString(x_left + pad2, lower_card_y + card_h2 - 24, f"Period Details : {data['comparison_data']['left']['period']} vs {data['comparison_data']['right']['period']}")
    pdf.setFillColor(colors.HexColor("#f1f5f9"))
    draw_table(pdf, padding, lower_card_y + card_h2 - 58, page_width_points - 2 * padding, 24, 8, "Header")
    pdf.setFillColor(TEXT)
    pdf.setFont("Poppins-Regular", 8)
    # Dynamic header: Period | <months...> | Total  (months can be 3, 6, up to 12)
    months_for_header = (month_keys or [])[:12]
    col_count = max(2, len(months_for_header) + 2)
    header_x0 = padding
    header_w = page_width_points - 2 * padding
    col_w = header_w / float(col_count)
    header_y = lower_card_y + card_h2 - 50
    # First column: Period
    pdf.drawCentredString(header_x0 + (0.5 * col_w), header_y, "Period")
    # Middle columns: months
    for idx, mk in enumerate(months_for_header, start=1):
        pdf.drawCentredString(header_x0 + (idx + 0.5) * col_w, header_y, _month_label(mk))
    # Last column: Total
    pdf.drawCentredString(header_x0 + (col_count - 0.5) * col_w, header_y, "Total")
    # Two rows below header: Left period row, Right period row
    row_h = 32
    first_row_y = (lower_card_y + card_h2 - 58) - row_h
    second_row_y = first_row_y - row_h
    third_row_y = second_row_y - row_h
    # Draw row backgrounds
    pdf.setFillColor(WHITE)
    draw_table(pdf, padding, first_row_y, page_width_points - 2 * padding, row_h, 8, "Body")
    draw_table(pdf, padding, second_row_y, page_width_points - 2 * padding, row_h, 8, "Body")
    draw_table(pdf, padding, third_row_y, page_width_points - 2 * padding, row_h, 8, "Footer")
    # Draw row contents
    pdf.setFillColor(TEXT)
    pdf.setFont("Poppins-Regular", 8)
    y_text_1 = first_row_y + 12
    y_text_2 = second_row_y + 12
    y_text_3 = third_row_y + 12
    # Left row label (Period column)
    pdf.drawString(header_x0 + 16, y_text_1, str(series_a_label or "Left"))
    # Right row label (Period column)
    pdf.drawString(header_x0 + 16, y_text_2, str(series_b_label or "Right"))
    # Total delta row label
    pdf.drawString(header_x0 + 16, y_text_3, "Total")
    # Month columns values
    left_total = 0.0
    right_total = 0.0
    for idx, mk in enumerate(months_for_header, start=1):
        lv = float(left_months.get(mk, 0) or 0)
        rv = float(right_months.get(mk, 0) or 0)
        left_total += lv
        right_total += rv
        cx = header_x0 + (idx + 0.5) * col_w
        pdf.drawCentredString(cx, y_text_1, _format_number(lv))
        pdf.drawCentredString(cx, y_text_2, _format_number(rv))
        # delta with sign for total row
        delta = rv - lv
        abs_delta = abs(delta)
        sign = "+" if delta >= 0 else "-"
        pdf.drawCentredString(cx, y_text_3, f"{sign}{_format_number(abs_delta)}")
    # Totals in last column
    cx_total = header_x0 + (col_count - 0.5) * col_w
    pdf.drawCentredString(cx_total, y_text_1, _format_number(left_total))
    pdf.drawCentredString(cx_total, y_text_2, _format_number(right_total))
    total_delta = right_total - left_total
    abs_total_delta = abs(total_delta)
    sign_total = "+" if total_delta >= 0 else "-"
    pdf.drawCentredString(cx_total, y_text_3, f"{sign_total}{_format_number(abs_total_delta)}")
    _footer(pdf, page_width_points)

def draw_main_materials(pdf, page_width_points: float, page_height_points: float, data: dict) -> None:
    padding = 0.78 * inch
    pdf.showPage()  # New page
    _header(pdf, page_width_points, page_height_points, data)
    _sub_header(pdf, page_width_points, page_height_points, data, "Main Materials")
    margin = padding
    gap = 0.3 * inch
    bar_card = (page_width_points - 2 * margin - gap) * 0.7
    pie_card = (page_width_points - 2 * margin - gap) * 0.3
    card_h2 = 3.8 * inch
    card_y2 = 2 * inch
    x_left = margin
    x_right = margin + bar_card + gap
    _rounded_card(pdf, x_left, card_y2 - 0.2 * inch, bar_card, card_h2 + 0.2 * inch, radius=8, fill=WHITE)
    _rounded_card(pdf, x_right, card_y2 - 0.2 * inch, pie_card, card_h2 + 0.2 * inch, radius=8, fill=WHITE)

    # --------- Left card: Top Materials by Quantity (5–8 horizontal bars) ----------
    items = (data.get("main_materials_data", {}) or {}).get("porportions", []) or []
    items_sorted = sorted(
        (it for it in items if isinstance(it, dict) and "total_waste" in it),
        key=lambda d: float(d.get("total_waste", 0) or 0),
        reverse=True,
    )
    top_n = min(5, max(1, len(items_sorted)))
    items_top = items_sorted[:top_n]

    # Layout inside left card
    pad = 24
    title_y = card_y2 + card_h2 - 28
    # ---------- wrapped label area logic ----------
    pdf.setFont("Poppins-Regular", 10)
    max_label_area = bar_card * 0.45     # Never exceed 45% of card width
    min_label_area = 60                  # Must be at least this wide

    # Compute needed width based on longest word (to avoid infinite wrapping)
    longest_word_w = max(
        (stringWidth(w, "Poppins-Regular", 10)
        for it in items_top
        for w in str(it.get("main_material_name", "")).split()),
        default=40
    )

    label_area = max(min_label_area, longest_word_w + 6)
    label_area = min(label_area, max_label_area)

    # Chart shrinks based on label area
    chart_left = x_left + pad + label_area + 8
    chart_right = x_left + bar_card - pad
    chart_w = max(1.0, chart_right - chart_left)

    chart_left = x_left + pad + label_area + 8
    chart_right = x_left + bar_card - pad
    chart_bottom = card_y2 + 28
    chart_top = card_y2 + card_h2 - 40
    chart_w = max(1.0, chart_right - chart_left)
    chart_h = max(1.0, chart_top - chart_bottom)

    # Title
    pdf.setFillColor(TEXT)
    pdf.setFont("Poppins-Medium", 12)
    pdf.drawString(x_left + pad, title_y, "Top Materials by Quantity")

    # X-axis ticks (nice)
    max_val = max([1.0] + [float(it.get("total_waste", 0) or 0) for it in items_top])
    mag = 1.0
    while mag * 10 <= max_val:
        mag *= 10.0
    for mul in (1.0, 2.0, 2.5, 5.0, 10.0):
        top_val = mul * mag
        if top_val >= max_val:
            break
    ticks = [0.0, top_val / 2.0, top_val]
    pdf.setStrokeColor(STROKE)
    pdf.setLineWidth(0.5)
    for tv in ticks:
        x = chart_left + (tv / top_val) * chart_w
        pdf.line(x, chart_bottom, x, chart_top)
        # tick labels
        lbl = _format_number(round(tv))
        lw = stringWidth(lbl, "Poppins-Regular", 9)
        pdf.setFillColor(TEXT)
        pdf.setFont("Poppins-Regular", 9)
        pdf.drawCentredString(x, chart_bottom - 12, lbl)
    # x-axis label "Kg."
    pdf.setFillColor(TEXT)
    pdf.setFont("Poppins-Regular", 10)
    pdf.drawRightString(chart_right + 12, chart_bottom - 26, "Kg.")

    # Helper: draw rectangle rounded only at the right end (outer), small radius
    def _draw_right_round_rect(x, y, w, h, r, color):
        if w <= 0 or h <= 0:
            return
        rr = max(0.0, min(r, h / 2.0, w))
        p = pdf.beginPath()
        # start at bottom-left
        p.moveTo(x, y)
        p.lineTo(x + w - rr, y)                  # bottom edge to start of arc
        p.arcTo(x + w - 2 * rr, y, x + w, y + 2 * rr, startAng=270, extent=90)  # bottom-right
        p.lineTo(x + w, y + h - rr)              # right edge up
        p.arcTo(x + w - 2 * rr, y + h - 2 * rr, x + w, y + h, startAng=0, extent=90)  # top-right
        p.lineTo(x, y + h)                       # top edge back to left (square)
        p.lineTo(x, y)                           # left edge down
        pdf.setFillColor(color)
        pdf.drawPath(p, stroke=0, fill=1)

    # Bars and labels (evenly spaced for up to 5 bars)
    groups = max(1, len(items_top))
    # bar height relative to available height; ensure reasonable thickness
    row_h = min(26.0, max(16.0, chart_h / (groups * 1.8)))
    cap_r = min(6.0, row_h * 0.4)
    # equal centers across chart area
    step = chart_h / (groups + 1)
    for i, it in enumerate(items_top):
        center_y = chart_bottom + (groups - i) * step  # evenly spaced centers from bottom to top
        y_bar = center_y - (row_h / 2.0)
        value = float(it.get("total_waste", 0) or 0)
        w = (value / top_val) * chart_w
        # bar with right-only small roundness
        bar_color = main_material_colorPalette[i % len(main_material_colorPalette)]
        _draw_right_round_rect(chart_left, y_bar, w, row_h, cap_r, bar_color)
        # ---------- wrapped label drawing ----------
        name = str(it.get("main_material_name", ""))

        label_lines = wrap_label(name, "Poppins-Regular", 10, label_area)

        pdf.setFillColor(TEXT)
        pdf.setFont("Poppins-Regular", 10)

        # multi-line vertical centering
        total_label_h = len(label_lines) * 11   # approx line height
        label_y_start = y_bar + (row_h - total_label_h) / 2 + 2

        for j, line in enumerate(label_lines):
            y_line = label_y_start + (len(label_lines) - 1 - j) * 11
            pdf.drawRightString(chart_left - 10, y_line, line)

        # value label: inside if fits, else outside
        val_text = _format_number(value)
        sw = stringWidth(val_text, "Poppins-Regular", 10)
        inside_space = max(0.0, w - cap_r - 8)
        pdf.setFont("Poppins-Regular", 10)
        if sw <= inside_space and w > 0:
            pdf.setFillColor(WHITE if BAR2 != WHITE else TEXT)
            pdf.drawRightString(chart_left + w - cap_r - 6, y_bar + row_h / 2.0 - 4, val_text)
        else:
            pdf.setFillColor(TEXT)
            x_out = min(chart_right - 4 - sw, chart_left + w + 6)
            pdf.drawString(x_out, y_bar + row_h / 2.0 - 4, val_text)

    # --------- Right card: Simple Pie Chart (all materials) ----------
    items_all = items_sorted  # include all items for pie
    pie_values = [float(it.get("total_waste", 0) or 0) for it in items_all] or [1.0]
    pie_colors = [colors.HexColor(main_material_colorPalette[i % len(main_material_colorPalette)]) for i in range(len(items_all))] or [BAR2]
    # smaller pie size (about half of the available dimension, with a sensible minimum)
    pie_size = max(60.0, min(pie_card, card_h2) * 0.6)
    pie_x = x_right + (pie_card - pie_size) / 2.0
    pie_y = card_y2 + (card_h2 - pie_size) - 36
    pdf.setFillColor(TEXT)
    pdf.setFont("Poppins-Medium", 12)
    pdf.drawString(pie_x - 24, title_y, "Materials Proportion")
    _simple_pie_chart(pdf, pie_x, pie_y - 12, pie_size, pie_values, pie_colors, gap_width=1, gap_color=colors.white)

    # --------- Below pie: Top 5 materials list ----------
    top5 = items_top[:5]
    row_h = 14
    start_y = (pie_y - 12) - 22  # move list down by additional 6
    left_x = x_right + 12
    right_x = x_right + pie_card - 12
    box_size = 8
    pdf.setFont("Poppins-Regular", 10)
    for i, it in enumerate(top5):
        y = start_y - i * (row_h + 6)  # a little more spacing between rows
        # color box
        c = colors.HexColor(main_material_colorPalette[i % len(main_material_colorPalette)])
        pdf.setFillColor(c)
        pdf.roundRect(left_x, y - box_size + 7, box_size, box_size, 2, stroke=0, fill=1)
        # name (truncate if necessary)
        name = str(it.get("main_material_name", ""))
        pdf.setFillColor(TEXT)
        max_name_w = (right_x - left_x) - box_size - 54  # leave room for percentage
        label = name
        while stringWidth(label, "Poppins-Regular", 10) > max_name_w and len(label) > 1:
            label = label[:-2] + "…"
        pdf.drawString(left_x + box_size + 6, y, label)
        # percentage on right
        perc = it.get("proportion_percent")
        if perc is None:
            # fallback compute from totals
            total_w = float((data.get("main_materials_data", {}) or {}).get("total_waste", 0) or 0) or sum(pie_values) or 1.0
            perc = (float(it.get("total_waste", 0) or 0) / total_w) * 100.0
        perc_text = f"{float(perc):.2f}%"
        pw = stringWidth(perc_text, "Poppins-Regular", 10)
        pdf.drawString(right_x - pw, y, perc_text)
    _footer(pdf, page_width_points)

def draw_main_materials_table(pdf, page_width_points: float, page_height_points: float, data: dict) -> None:
    padding = 0.78 * inch
    mats_per_page = 7
    total_mats = len(data["main_materials_data"]["porportions"])
    for page_idx in range(0, total_mats, mats_per_page):
        pdf.showPage()  # New page
        _header(pdf, page_width_points, page_height_points, data)
        _sub_header(pdf, page_width_points, page_height_points, data, "Main Materials")
        # --------- Table of materials list ----------
        # pdf.setFillColor(TEXT)
        # pdf.setFont("Poppins-Medium", 12)
        # pdf.drawString(x_left, card_y2 - 36, f"Materials List {data['date_from']} - {data['date_to']}")
        pdf.setFillColor(colors.HexColor("#f1f5f9"))
        draw_table(pdf, padding, page_height_points - (3 * inch), page_width_points - 2 * padding, 24, 8, "Header")
        pdf.setFillColor(TEXT)
        pdf.setFont("Poppins-Regular", 8)
        pdf.drawString(padding + 16, page_height_points - (2.88 * inch), "Main Material")
        pdf.drawString(padding + 3.2 * inch, page_height_points - (2.88 * inch), "Total Waste (kg)")
        pdf.drawString(padding + 5.8 * inch, page_height_points - (2.88 * inch), "Percentage (%)")
        pdf.drawString(padding + 8.5 * inch, page_height_points - (2.88 * inch), "GHG Reduction (kgCO2e)")
        page_mats = data["main_materials_data"]["porportions"][page_idx:page_idx + mats_per_page]
        for idx, mat in enumerate(page_mats):
            y_base = page_height_points - (3 * inch) - 32 - (idx * 32)

            # Use 'Footer' if last row on page, else 'Body'
            table_type = "Footer" if idx == len(page_mats) - 1 else "Body"
            pdf.setFillColor(WHITE)
            draw_table(pdf, padding, y_base, page_width_points - 2 * padding, 32, 8, table_type)
            pdf.setFillColor(TEXT)
            pdf.setFont("Poppins-Regular", 8)
            y_text = y_base + 12  # Align text in table row
            pdf.drawString(padding + 16, y_text, mat["main_material_name"])
            pdf.drawString(padding + 3.2 * inch, y_text, _format_number(mat["total_waste"]))
            pdf.drawString(padding + 5.8 * inch, y_text, f"{mat['proportion_percent']:.2f}%")
            pdf.drawString(padding + 8.5 * inch, y_text, _format_number(mat["ghg_reduction"]))
        _footer(pdf, page_width_points)

def draw_sub_materials(pdf, page_width_points: float, page_height_points: float, data: dict) -> None:
    padding = 0.78 * inch
    pdf.showPage()  # New page
    _header(pdf, page_width_points, page_height_points, data)
    _sub_header(pdf, page_width_points, page_height_points, data, "Sub Materials")
    margin = padding
    gap = 0.3 * inch
    bar_card = (page_width_points - 2 * margin - gap) * 0.7
    pie_card = (page_width_points - 2 * margin - gap) * 0.3
    card_h2 = 3.8 * inch
    card_y2 = 2 * inch
    x_left = margin
    x_right = margin + bar_card + gap
    _rounded_card(pdf, x_left, card_y2 - 0.2 * inch, bar_card, card_h2 + 0.2 * inch, radius=8, fill=WHITE)
    _rounded_card(pdf, x_right, card_y2 - 0.2 * inch, pie_card, card_h2 + 0.2 * inch, radius=8, fill=WHITE)

    # --------- Left card: Top Materials by Quantity (5–8 horizontal bars) ----------
    items = (data.get("sub_materials_data", {}) or {}).get("porportions", []) or []
    items_sorted = sorted(
        (it for it in items if isinstance(it, dict) and "total_waste" in it),
        key=lambda d: float(d.get("total_waste", 0) or 0),
        reverse=True,
    )
    top_n = min(5, max(1, len(items_sorted)))
    items_top = items_sorted[:top_n]

    # Layout inside left card
    pad = 24
    title_y = card_y2 + card_h2 - 28
    # ---------- wrapped label area logic ----------
    pdf.setFont("Poppins-Regular", 10)
    max_label_area = bar_card * 0.45     # Never exceed 45% of card width
    min_label_area = 60                  # Must be at least this wide

    # Compute needed width based on longest word (to avoid infinite wrapping)
    longest_word_w = max(
        (stringWidth(w, "Poppins-Regular", 10)
        for it in items_top
        for w in str(it.get("material_name", "")).split()),
        default=40
    )

    label_area = max(min_label_area, longest_word_w + 6)
    label_area = min(label_area, max_label_area)

    # Chart shrinks based on label area
    chart_left = x_left + pad + label_area + 8
    chart_right = x_left + bar_card - pad
    chart_w = max(1.0, chart_right - chart_left)

    chart_left = x_left + pad + label_area + 8
    chart_right = x_left + bar_card - pad
    chart_bottom = card_y2 + 28
    chart_top = card_y2 + card_h2 - 40
    chart_w = max(1.0, chart_right - chart_left)
    chart_h = max(1.0, chart_top - chart_bottom)

    # Title
    pdf.setFillColor(TEXT)
    pdf.setFont("Poppins-Medium", 12)
    pdf.drawString(x_left + pad, title_y, "Top Materials by Quantity")

    # X-axis ticks (nice)
    max_val = max([1.0] + [float(it.get("total_waste", 0) or 0) for it in items_top])
    mag = 1.0
    while mag * 10 <= max_val:
        mag *= 10.0
    for mul in (1.0, 2.0, 2.5, 5.0, 10.0):
        top_val = mul * mag
        if top_val >= max_val:
            break
    ticks = [0.0, top_val / 2.0, top_val]
    pdf.setStrokeColor(STROKE)
    pdf.setLineWidth(0.5)
    for tv in ticks:
        x = chart_left + (tv / top_val) * chart_w
        pdf.line(x, chart_bottom, x, chart_top)
        # tick labels
        lbl = _format_number(round(tv))
        lw = stringWidth(lbl, "Poppins-Regular", 9)
        pdf.setFillColor(TEXT)
        pdf.setFont("Poppins-Regular", 9)
        pdf.drawCentredString(x, chart_bottom - 12, lbl)
    # x-axis label "Kg."
    pdf.setFillColor(TEXT)
    pdf.setFont("Poppins-Regular", 10)
    pdf.drawRightString(chart_right + 12, chart_bottom - 26, "Kg.")

    # Helper: draw rectangle rounded only at the right end (outer), small radius
    def _draw_right_round_rect(x, y, w, h, r, color):
        if w <= 0 or h <= 0:
            return
        rr = max(0.0, min(r, h / 2.0, w))
        p = pdf.beginPath()
        # start at bottom-left
        p.moveTo(x, y)
        p.lineTo(x + w - rr, y)                  # bottom edge to start of arc
        p.arcTo(x + w - 2 * rr, y, x + w, y + 2 * rr, startAng=270, extent=90)  # bottom-right
        p.lineTo(x + w, y + h - rr)              # right edge up
        p.arcTo(x + w - 2 * rr, y + h - 2 * rr, x + w, y + h, startAng=0, extent=90)  # top-right
        p.lineTo(x, y + h)                       # top edge back to left (square)
        p.lineTo(x, y)                           # left edge down
        pdf.setFillColor(color)
        pdf.drawPath(p, stroke=0, fill=1)

    # Bars and labels (evenly spaced for up to 5 bars)
    groups = max(1, len(items_top))
    # bar height relative to available height; ensure reasonable thickness
    row_h = min(26.0, max(16.0, chart_h / (groups * 1.8)))
    cap_r = min(6.0, row_h * 0.4)
    # equal centers across chart area
    step = chart_h / (groups + 1)
    for i, it in enumerate(items_top):
        center_y = chart_bottom + (groups - i) * step  # evenly spaced centers from bottom to top
        y_bar = center_y - (row_h / 2.0)
        value = float(it.get("total_waste", 0) or 0)
        w = (value / top_val) * chart_w
        # bar with right-only small roundness
        bar_color = sub_material_colorPalette[i % len(sub_material_colorPalette)]
        _draw_right_round_rect(chart_left, y_bar, w, row_h, cap_r, bar_color)
        # ---------- wrapped label drawing ----------
        name = str(it.get("material_name", ""))

        label_lines = wrap_label(name, "Poppins-Regular", 10, label_area)

        pdf.setFillColor(TEXT)
        pdf.setFont("Poppins-Regular", 10)

        # multi-line vertical centering
        total_label_h = len(label_lines) * 11   # approx line height
        label_y_start = y_bar + (row_h - total_label_h) / 2 + 2

        for j, line in enumerate(label_lines):
            y_line = label_y_start + (len(label_lines) - 1 - j) * 11
            pdf.drawRightString(chart_left - 10, y_line, line)

        # value label: inside if fits, else outside
        val_text = _format_number(value)
        sw = stringWidth(val_text, "Poppins-Regular", 10)
        inside_space = max(0.0, w - cap_r - 8)
        pdf.setFont("Poppins-Regular", 10)
        if sw <= inside_space and w > 0:
            pdf.setFillColor(WHITE if BAR2 != WHITE else TEXT)
            pdf.drawRightString(chart_left + w - cap_r - 6, y_bar + row_h / 2.0 - 4, val_text)
        else:
            pdf.setFillColor(TEXT)
            x_out = min(chart_right - 4 - sw, chart_left + w + 6)
            pdf.drawString(x_out, y_bar + row_h / 2.0 - 4, val_text)

    # --------- Right card: Simple Pie Chart (all materials) ----------
    items_all = items_sorted  # include all items for pie
    pie_values = [float(it.get("total_waste", 0) or 0) for it in items_all] or [1.0]
    pie_colors = [colors.HexColor(sub_material_colorPalette[i % len(sub_material_colorPalette)]) for i in range(len(items_all))] or [BAR2]
    # smaller pie size (about half of the available dimension, with a sensible minimum)
    pie_size = max(60.0, min(pie_card, card_h2) * 0.6)
    pie_x = x_right + (pie_card - pie_size) / 2.0
    pie_y = card_y2 + (card_h2 - pie_size) - 36
    pdf.setFillColor(TEXT)
    pdf.setFont("Poppins-Medium", 12)
    pdf.drawString(pie_x - 24, title_y, "Materials Proportion")
    _simple_pie_chart(pdf, pie_x, pie_y - 12, pie_size, pie_values, pie_colors, gap_width=1, gap_color=colors.white)

    # --------- Below pie: Top 5 materials list ----------
    top5 = items_top[:5]
    row_h = 14
    start_y = (pie_y - 12) - 22  # move list down by additional 6
    left_x = x_right + 12
    right_x = x_right + pie_card - 12
    box_size = 8
    pdf.setFont("Poppins-Regular", 10)
    for i, it in enumerate(top5):
        y = start_y - i * (row_h + 6)  # a little more spacing between rows
        # color box
        c = colors.HexColor(sub_material_colorPalette[i % len(sub_material_colorPalette)])
        pdf.setFillColor(c)
        pdf.roundRect(left_x, y - box_size + 7, box_size, box_size, 2, stroke=0, fill=1)
        # name (truncate if necessary)
        name = str(it.get("material_name", ""))
        pdf.setFillColor(TEXT)
        max_name_w = (right_x - left_x) - box_size - 54  # leave room for percentage
        label = name
        while stringWidth(label, "Poppins-Regular", 10) > max_name_w and len(label) > 1:
            label = label[:-2] + "…"
        pdf.drawString(left_x + box_size + 6, y, label)
        # percentage on right
        perc = it.get("proportion_percent")
        if perc is None:
            # fallback compute from totals
            total_w = float((data.get("sub_materials_data", {}) or {}).get("total_waste", 0) or 0) or sum(pie_values) or 1.0
            perc = (float(it.get("total_waste", 0) or 0) / total_w) * 100.0
        perc_text = f"{float(perc):.2f}%"
        pw = stringWidth(perc_text, "Poppins-Regular", 10)
        pdf.drawString(right_x - pw, y, perc_text)
    _footer(pdf, page_width_points)

def draw_sub_materials_table(pdf, page_width_points: float, page_height_points: float, data: dict) -> None:
    padding = 0.78 * inch
    rows_per_page = 7  # limit rows, including group headers
    grouped = (data.get("sub_materials_data", {}) or {}).get("porportions_grouped", {}) or {}

    # Build a flat sequence of rows: ('group', name) or ('item', dict)
    flat_rows = []
    for group_name, items in grouped.items():
        flat_rows.append(("group", group_name))
        for item in items or []:
            flat_rows.append(("item", item))

    total_rows = len(flat_rows)
    for start_idx in range(0, total_rows, rows_per_page):
        page_rows = flat_rows[start_idx:start_idx + rows_per_page]
        pdf.showPage()  # New page
        _header(pdf, page_width_points, page_height_points, data)
        _sub_header(pdf, page_width_points, page_height_points, data, "Sub Materials")

        # Table header
        pdf.setFillColor(colors.HexColor("#f1f5f9"))
        draw_table(pdf, padding, page_height_points - (3 * inch), page_width_points - 2 * padding, 24, 8, "Header")
        pdf.setFillColor(TEXT)
        pdf.setFont("Poppins-Regular", 8)
        pdf.drawString(padding + 16, page_height_points - (2.88 * inch), "Sub Material")
        pdf.drawString(padding + 3.2 * inch, page_height_points - (2.88 * inch), "Total Waste (kg)")
        pdf.drawString(padding + 5.8 * inch, page_height_points - (2.88 * inch), "Percentage (%)")
        pdf.drawString(padding + 8.5 * inch, page_height_points - (2.88 * inch), "GHG Reduction (kgCO2e)")

        # Data rows (including group header rows)
        for idx, (row_type, payload) in enumerate(page_rows):
            y_base = page_height_points - (3 * inch) - 32 - (idx * 32)
            table_type = "Footer" if idx == len(page_rows) - 1 else "Body"

            if row_type == "group":
                # Grey background full-width row with group name
                pdf.setFillColor(colors.HexColor("#f1f5f9"))
                draw_table(pdf, padding, y_base, page_width_points - 2 * padding, 32, 8, table_type)
                pdf.setFillColor(TEXT)
                pdf.setFont("Poppins-Medium", 9)
                pdf.drawString(padding + 16, y_base + 12, str(payload))
            else:
                mat = payload
                pdf.setFillColor(WHITE)
                draw_table(pdf, padding, y_base, page_width_points - 2 * padding, 32, 8, table_type)
                pdf.setFillColor(TEXT)
                pdf.setFont("Poppins-Regular", 8)
                y_text = y_base + 12  # Align text in table row
                pdf.drawString(padding + 16, y_text, str(mat.get("material_name", "")))
                pdf.drawString(padding + 3.2 * inch, y_text, _format_number(mat.get("total_waste", 0)))
                pdf.drawString(padding + 5.8 * inch, y_text, f"{float(mat.get('proportion_percent', 0) or 0):.2f}%")
                pdf.drawString(padding + 8.5 * inch, y_text, _format_number(mat.get("ghg_reduction", 0)))

        _footer(pdf, page_width_points)


def draw_waste_diversion(pdf, page_width_points: float, page_height_points: float, data: dict) -> None:
    pdf.showPage()
    padding = 0.78 * inch
    _header(pdf, page_width_points, page_height_points, data)
    _sub_header(pdf, page_width_points, page_height_points, data, "Waste Diversion")
    
    # Top row: 4 stat chips
    card_data = ((data.get("diversion_data", {}) or {}).get("card_data", {}) or {})
    total_origin = card_data.get("total_origin", 0)
    complete_transfer = card_data.get("complete_transfer", 0)
    processing_transfer = card_data.get("processing_transfer", 0)
    completed_rate = card_data.get("completed_rate", 0)

    # Layout dimensions
    margin = padding
    content_top = page_height_points - 2.2 * inch
    chip_gap = 12
    usable_w = (page_width_points - 2 * margin)
    chip_w = max(1.0, (usable_w - (3 * chip_gap)) / 4.0)
    chip_h = 0.60 * inch
    chip_y = content_top - chip_h

    # Draw 4 chips
    x0 = margin
    _stat_chip(pdf, x0, chip_y, chip_w, chip_h, "Total Origins", total_origin)
    _stat_chip(pdf, x0 + (chip_w + chip_gap), chip_y, chip_w, chip_h, "Complete Transfers", f"{float(complete_transfer or 0):.0f}%")
    _stat_chip(pdf, x0 + 2 * (chip_w + chip_gap), chip_y, chip_w, chip_h, "Processing Transfers", f"{float(processing_transfer or 0):.0f}%")
    _stat_chip(pdf, x0 + 3 * (chip_w + chip_gap), chip_y, chip_w, chip_h, "Completed Rate", f"{float(completed_rate or 0):.0f}%")

    # --- SANKEY CHART SECTION ---
    
    # Extract Sankey Data
    sankey_raw = (data.get("diversion_data", {}) or {}).get("sankey_data", [])
    if sankey_raw and len(sankey_raw) > 1:
        # Define chart area (below chips, above footer)
        chart_y_top = chip_y - 30  # 30pt gap below chips
        chart_height = chart_y_top - (1.5 * inch) # Leave space for footer
        
        _draw_sankey_diagram(
            pdf, 
            x=margin, 
            y_top=chart_y_top, 
            width=usable_w, 
            height=chart_height, 
            data_rows=sankey_raw
        )

    _footer(pdf, page_width_points)

def _draw_sankey_diagram(pdf, x, y_top, width, height, data_rows):
    """
    Draws a Sankey diagram using ReportLab primitives without external libs.
    """
    # 1. Parse Data Structure
    # Skip header row if present
    rows = data_rows[1:] if data_rows[0][0] == "From" else data_rows
    
    sources = {} # {name: total_weight}
    targets = {} # {name: total_weight}
    flows = []   # [{source, target, value}]

    # Aggregate totals
    for s, t, w in rows:
        w = float(w)
        if w <= 0: continue
        sources[s] = sources.get(s, 0) + w
        targets[t] = targets.get(t, 0) + w
        flows.append({'source': s, 'target': t, 'value': w})

    # 2. Layout Calculations
    node_gap = 10 # Vertical gap between bars
    
    total_source_weight = sum(sources.values())
    total_target_weight = sum(targets.values())
    
    # Calculate height occupied by gaps
    source_gaps = (len(sources) - 1) * node_gap if len(sources) > 0 else 0
    target_gaps = (len(targets) - 1) * node_gap if len(targets) > 0 else 0
    
    # Determine Scale (pixels per unit of weight)
    # We check which side is the "limiting factor" (taller side)
    if total_source_weight > 0 and total_target_weight > 0:
        # Calculate potential scales for both sides to fit in 'height'
        scale_s = (height - source_gaps) / total_source_weight
        scale_t = (height - target_gaps) / total_target_weight
        scale = min(scale_s, scale_t)
    else:
        scale = 1.0

    # 3. Sort Nodes (Heuristic)
    # Sort Targets: Composted (top) vs Incineration (bottom)
    # We assume alphabetical order puts "Composted" before "Incineration", or custom sort:
    target_names = sorted(targets.keys(), key=lambda x: "Incineration" in x)
    
    # Sort Sources based on weighted destination
    target_indices = {name: i for i, name in enumerate(target_names)}
    source_scores = {}
    for name in sources:
        my_flows = [f for f in flows if f['source'] == name]
        if not my_flows:
            source_scores[name] = 0
            continue
        weighted_pos = sum(f['value'] * target_indices.get(f['target'], 0) for f in my_flows)
        total_w = sum(f['value'] for f in my_flows)
        source_scores[name] = weighted_pos / total_w

    source_names = sorted(sources.keys(), key=lambda x: (source_scores.get(x, 0), -sources[x]))

    # 4. Calculate Node Coordinates with Vertical Centering
    source_coords = {} 
    target_coords = {} 
    
    # Calculate total visual height of both columns
    h_sources_total = sum(sources[n] * scale for n in sources) + source_gaps
    h_targets_total = sum(targets[n] * scale for n in targets) + target_gaps
    
    # Determine the maximum used height (usually close to 'height')
    max_used_height = max(h_sources_total, h_targets_total)
    
    # Calculate starting Y positions to center the columns relative to each other
    # y_top is the absolute top. We push down by half the difference.
    y_source_start = y_top - (max_used_height - h_sources_total) / 2
    y_target_start = y_top - (max_used_height - h_targets_total) / 2

    # Left Side Positioning
    curr_y = y_source_start
    for name in source_names:
        h = sources[name] * scale
        source_coords[name] = {'y': curr_y, 'h': h, 'offset': 0}
        curr_y -= (h + node_gap)

    # Right Side Positioning
    curr_y = y_target_start
    for name in target_names:
        h = targets[name] * scale
        target_coords[name] = {'y': curr_y, 'h': h, 'offset': 0}
        curr_y -= (h + node_gap)

    # 5. Draw Links (Bezier Curves)
    bar_width = 6
    link_color = colors.Color(0.85, 0.85, 0.85, alpha=0.6)

    pdf.saveState()
    for s_name in source_names:
        s_flows = sorted([f for f in flows if f['source'] == s_name], 
                         key=lambda x: target_indices.get(x['target'], 0))
        
        for flow in s_flows:
            t_name = flow['target']
            val = flow['value']
            link_h = val * scale
            
            s_node = source_coords[s_name]
            t_node = target_coords[t_name]
            
            y_start = s_node['y'] - s_node['offset']
            y_end = t_node['y'] - t_node['offset']
            
            s_node['offset'] += link_h
            t_node['offset'] += link_h

            # REMOVED THE GAP: connect exactly to bar_width
            x_start = x + bar_width 
            x_end = x + width - bar_width
            
            # Bezier Control Points
            dist = (x_end - x_start) * 0.4
            cp1 = (x_start + dist, y_start)
            cp2 = (x_end - dist, y_end)
            cp1_b = (x_start + dist, y_start - link_h)
            cp2_b = (x_end - dist, y_end - link_h)

            p = pdf.beginPath()
            p.moveTo(x_start, y_start)
            p.curveTo(cp1[0], cp1[1], cp2[0], cp2[1], x_end, y_end)
            p.lineTo(x_end, y_end - link_h)
            p.curveTo(cp2_b[0], cp2_b[1], cp1_b[0], cp1_b[1], x_start, y_start - link_h)
            p.close()
            
            pdf.setFillColor(link_color)
            pdf.setStrokeColor(link_color)
            pdf.drawPath(p, fill=1, stroke=0)
            
    pdf.restoreState()

    # 6. Draw Node Bars and Labels
    pdf.setFont("Helvetica-Bold", 8)
    text_color = colors.Color(0.4, 0.4, 0.4)
    source_colors = [colors.Color(0.4, 0.6, 0.9), colors.Color(0.4, 0.8, 0.5), colors.lightgrey]
    
    # Draw Sources
    for i, name in enumerate(source_names):
        data = source_coords[name]
        bar_y = data['y'] - data['h']
        col = source_colors[i % len(source_colors)]
        pdf.setFillColor(col)
        pdf.setStrokeColor(col)
        pdf.rect(x, bar_y, bar_width, data['h'], fill=1, stroke=0)
        pdf.setFillColor(text_color)
        pdf.drawString(x + bar_width + 8, bar_y + data['h']/2 - 3, name)

    # Draw Targets
    pdf.setFont("Helvetica-Bold", 9)
    target_bar_color = colors.Color(0.3, 0.6, 0.9)
    
    for name in target_names:
        data = target_coords[name]
        bar_y = data['y'] - data['h']
        pdf.setFillColor(target_bar_color)
        pdf.setStrokeColor(target_bar_color)
        pdf.rect(x + width - bar_width, bar_y, bar_width, data['h'], fill=1, stroke=0)
        pdf.setFillColor(text_color)
        text_w = pdf.stringWidth(name, "Helvetica-Bold", 9)
        pdf.drawString(x + width - bar_width - 8 - text_w, bar_y + data['h']/2 - 3, name)

def draw_waste_diversion_table(pdf, page_width_points: float, page_height_points: float, data: dict) -> None:
    padding = 0.78 * inch
    rows = (((data.get("diversion_data", {}) or {}).get("material_table", []) or []))
    if not isinstance(rows, list):
        rows = []

    # Layout constants
    header_y = page_height_points - (3 * inch)
    header_h = 24

    content_x = padding
    content_w = page_width_points - 2 * padding

    # Columns: Materials | Jan..Dec (12 cols) | Status | Destination
    months = ["Jan","Feb","Mar","Apr","May","Jun","Jul","Aug","Sep","Oct","Nov","Dec"]
    # Allocate widths proportionally to fit page
    materials_w = content_w * 0.22
    month_w = content_w * 0.045
    status_w = content_w * 0.10
    destination_w = max(1.0, content_w - (materials_w + month_w * 12 + status_w))

    def col_x_for_month(i: int) -> float:
        return content_x + materials_w + (i * month_w)

    def fit_text(text: str, max_w: float) -> str:
        t = str(text or "")
        if stringWidth(t, "Poppins-Regular", 8) <= max_w:
            return t
        # Trim with ellipsis
        ell = "…"
        while t and stringWidth(t + ell, "Poppins-Regular", 8) > max_w:
            t = t[:-1]
        return (t + ell) if t else ell

    total_rows = len(rows)
    min_y = 1.5 * inch
    line_h = 10
    group_gap = 4

    def destination_groups(row) -> list[list[str]]:
        """
        Returns a list of wrapped-line groups, one group per destination item.
        Each inner list contains the wrapped lines for that item.
        """
        dest_val = row.get("destination", [])
        parts = dest_val if isinstance(dest_val, list) else [str(dest_val)]
        groups: list[list[str]] = []
        pdf.setFont("Poppins-Regular", 8)
        for part in (parts or ["-"]):
            wrapped = _wrap_text_lines(pdf, str(part), destination_w - 12, "Poppins-Regular", 8)
            groups.append(wrapped or ["-"])
        return groups

    def compute_row_height(row) -> float:
        groups = destination_groups(row)
        lines_count = sum(len(g) for g in groups)
        text_block_h = max(1, lines_count) * line_h + max(0, len(groups) - 1) * group_gap
        badge_h = 18
        return max(32, text_block_h + 12, badge_h + 12)

    idx_global = 0
    # Ensure at least one page even if no rows
    while idx_global < total_rows or (total_rows == 0 and idx_global == 0):
        pdf.showPage()
        _header(pdf, page_width_points, page_height_points, data)
        _sub_header(pdf, page_width_points, page_height_points, data, "Waste Diversion")

        # Header band
        pdf.setFillColor(colors.HexColor("#f1f5f9"))
        draw_table(pdf, content_x, header_y, content_w, header_h, 8, "Header")
        pdf.setFillColor(TEXT)
        pdf.setFont("Poppins-Regular", 8)
        header_text_y = page_height_points - (2.88 * inch)

        # Header labels
        pdf.drawString(content_x + 16, header_text_y, "Materials")
        for i, m in enumerate(months):
            mx = col_x_for_month(i)
            pdf.drawString(mx + 4, header_text_y, m)
        status_x = content_x + materials_w + (len(months) * month_w)
        dest_x = status_x + status_w
        pdf.drawString(status_x + 4, header_text_y, "Status")
        pdf.drawString(dest_x + 4, header_text_y, "Destination")

        current_y = header_y
        drew_any = False
        while idx_global < total_rows:
            this_row = rows[idx_global]
            this_h = compute_row_height(this_row)
            # If this row doesn't fit, stop page
            if current_y - this_h < min_y:
                break

            # Determine if this is last row on this page (for footer style)
            next_h = compute_row_height(rows[idx_global + 1]) if (idx_global + 1) < total_rows else 0
            is_last_on_page = (current_y - this_h - next_h) < min_y or (idx_global + 1) >= total_rows

            y_base = current_y - this_h
            table_type = "Footer" if is_last_on_page else "Body"
            pdf.setFillColor(WHITE)
            draw_table(pdf, content_x, y_base, content_w, this_h, 8, table_type)
            pdf.setFillColor(TEXT)
            pdf.setFont("Poppins-Regular", 8)
            # Center-aligned baseline for simple cells
            y_text = y_base + (this_h / 2) - 4

            # Materials
            pdf.drawString(content_x + 16, y_text, str(this_row.get("materials", "")))

            # Month values
            month_values = {}
            try:
                for entry in (this_row.get("data", []) or []):
                    if isinstance(entry, dict):
                        month_values[str(entry.get("month"))] = float(entry.get("value", 0) or 0)
            except Exception:
                month_values = {}
            for i, m in enumerate(months):
                mx = col_x_for_month(i)
                val = month_values.get(m, 0)
                txt = _format_number(val)
                pdf.drawString(mx + 4, y_text, txt)

            # Status
            status_val = str(this_row.get("status", ""))
            if status_val.lower() == "processing":
                # Draw pill badge
                badge_bg = colors.HexColor("#FFF4E5")
                badge_text = colors.HexColor("#F59E0B")
                pdf.setFont("Poppins-Medium", 8)
                disp = fit_text(status_val, status_w - 16)
                tw = stringWidth(disp, "Poppins-Medium", 8)
                pad_x = 10
                badge_w = min(status_w - 8, tw + 2 * pad_x)
                badge_h = 18
                bx = status_x + 4
                by = y_base + (this_h - badge_h) / 2
                pdf.setFillColor(badge_bg)
                pdf.setStrokeColor(badge_bg)
                pdf.roundRect(bx, by, badge_w, badge_h, badge_h / 2, stroke=0, fill=1)
                pdf.setFillColor(badge_text)
                tx = bx + (badge_w - tw) / 2
                ty = by + (badge_h / 2) - 3
                pdf.drawString(tx, ty, disp)
                pdf.setFillColor(TEXT)
                pdf.setFont("Poppins-Regular", 8)
            elif status_val.lower().startswith("complete"):
                # Draw green success pill
                badge_bg = colors.HexColor("#EAF7F0")
                badge_text = colors.HexColor("#16A34A")
                pdf.setFont("Poppins-Medium", 8)
                disp = fit_text(status_val, status_w - 16)
                tw = stringWidth(disp, "Poppins-Medium", 8)
                pad_x = 10
                badge_w = min(status_w - 8, tw + 2 * pad_x)
                badge_h = 18
                bx = status_x + 4
                by = y_base + (this_h - badge_h) / 2
                pdf.setFillColor(badge_bg)
                pdf.setStrokeColor(badge_bg)
                pdf.roundRect(bx, by, badge_w, badge_h, badge_h / 2, stroke=0, fill=1)
                pdf.setFillColor(badge_text)
                tx = bx + (badge_w - tw) / 2
                ty = by + (badge_h / 2) - 3
                pdf.drawString(tx, ty, disp)
                pdf.setFillColor(TEXT)
                pdf.setFont("Poppins-Regular", 8)
            else:
                pdf.drawString(status_x + 4, y_text, fit_text(status_val, status_w - 8))

            # Destination: grouped with bullet markers and indentation
            pdf.setFont("Poppins-Regular", 8)
            groups = destination_groups(this_row)
            dy = y_base + this_h - 12
            text_x = dest_x + 12
            bullet_x = dest_x + 6
            placeholder_only = (len(groups) == 1 and len(groups[0]) == 1 and groups[0][0] == "-")
            if placeholder_only:
                # No bullet for placeholder; center "-" in the destination cell
                dash = "-"
                pdf.setFont("Poppins-Regular", 8)
                tw_dash = stringWidth(dash, "Poppins-Regular", 8)
                tx = dest_x + (destination_w - tw_dash) / 2
                pdf.drawString(tx, y_text, dash)
            else:
                for gi, group in enumerate(groups):
                    if group:
                        # draw a small bullet for the first line of this group
                        pdf.setFillColor(TEXT)
                        pdf.circle(bullet_x, dy - 3, 2, stroke=0, fill=1)
                        pdf.setFillColor(TEXT)
                        # first line
                        pdf.drawString(text_x, dy, group[0])
                        dy -= line_h
                        # continuation lines (no bullet)
                        for ln in group[1:]:
                            pdf.drawString(text_x, dy, ln)
                            dy -= line_h
                    # gap between groups
                    if gi < len(groups) - 1:
                        dy -= group_gap

            current_y = y_base
            idx_global += 1
            drew_any = True

        _footer(pdf, page_width_points)
def main() -> None:
    width_points = PAGE_WIDTH_IN * inch
    height_points = PAGE_HEIGHT_IN * inch
    pdfmetrics.registerFont(TTFont('Poppins-Bold', 'scripts/Poppins-Bold.ttf'))
    pdfmetrics.registerFont(TTFont('Poppins-Regular', 'scripts/Poppins-Regular.ttf'))
    pdfmetrics.registerFont(TTFont('Poppins-Medium', 'scripts/Poppins-Medium.ttf'))

    output_dir = Path("notebooks") / "output"
    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_dir / f"report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.pdf"

    pdf = canvas.Canvas(str(output_path), pagesize=(width_points, height_points))
    # Draw cover content
    draw_cover(pdf, width_points, height_points, data)
    draw_overview(pdf, width_points, height_points, data)
    for performance_data in data["performance_data"]:
        draw_performance(pdf, width_points, height_points, data, performance_data)
    draw_performance_table(pdf, width_points, height_points, data)
    draw_comparison_advice(pdf, width_points, height_points, data)
    draw_comparison(pdf, width_points, height_points, data)
    draw_main_materials(pdf, width_points, height_points, data)
    draw_main_materials_table(pdf, width_points, height_points, data)
    draw_sub_materials(pdf, width_points, height_points, data)
    draw_sub_materials_table(pdf, width_points, height_points, data)
    draw_waste_diversion(pdf, width_points, height_points, data)
    draw_waste_diversion_table(pdf, width_points, height_points, data)


    pdf.save()

    print(f"Saved: {output_path} ({PAGE_WIDTH_IN}in x {PAGE_HEIGHT_IN}in)")


if __name__ == "__main__":
    main()


