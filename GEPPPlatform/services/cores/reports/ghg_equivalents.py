"""GHG equivalence constants and conversion helpers.

Reference (T-VER, อบก. — Thailand Voluntary Emission Reduction Program):
    * 1 mature tree absorbs ~9.5 kgCO2eq per year
    * 1 rai of Thai forest absorbs ~950 kgCO2eq per year (~0.95 tCO2eq/rai/yr)
    * Typical tree density: ~100 trees per rai
    * Consistency check: 950 kgCO2eq/rai ÷ 100 trees/rai = 9.5 kgCO2eq/tree ✓

Always operate on kgCO2eq inputs. Convert tCO2eq → kgCO2eq before calling.
"""

KG_CO2_PER_TREE_PER_YEAR: float = 9.5
KG_CO2_PER_RAI_PER_YEAR: float = 950.0
TREES_PER_RAI: int = 100


def kg_co2_to_trees(kg_co2: float) -> float:
    if not kg_co2 or kg_co2 <= 0:
        return 0.0
    return kg_co2 / KG_CO2_PER_TREE_PER_YEAR


def kg_co2_to_forest_rai(kg_co2: float) -> float:
    if not kg_co2 or kg_co2 <= 0:
        return 0.0
    return kg_co2 / KG_CO2_PER_RAI_PER_YEAR
