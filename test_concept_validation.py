#!/usr/bin/env python3
"""
Test de validation du concept illustré dans le diagramme.
Ce test vérifie que l'algorithme groupe correctement les produits
selon la hiérarchie PS(A) → SF(A) → PF(A).
"""

import sys
import os
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from datetime import datetime, timedelta
from sothemalgo_grouper import ManufacturingOrder, BOMEntry, run_grouping_algorithm

def test_concept_validation():
    """
    Test basé sur le concept du diagramme :
    - Famille A : PS(A) → SF(A) → PF(A)
    - Tous doivent être groupés ensemble
    - Fenêtre basée sur la date PS
    """
    print("=== Test de validation du concept ===")
    
    # Dates de test
    base_date = datetime(2024, 1, 15)  # Lundi
    ps_date = base_date + timedelta(days=1)    # Mardi - PS(A)
    sf_date = base_date + timedelta(days=2)    # Mercredi - SF(A) 
    pf_date = base_date + timedelta(days=3)    # Jeudi - PF(A)
    
    # Créer les OFs selon le concept
    ofs = [
        # Produit Fini PF(A) - besoin client
        ManufacturingOrder("OF_PF_A_001", "PF_A", "PF_A", "PF", 3, pf_date.strftime('%Y-%m-%d'), 100, "Client", "A", "US1", "FS1"),
        
        # Semi-Fini SF(A) - composant intermédiaire
        ManufacturingOrder("OF_SF_A_001", "SF_A", "SF_A", "SF", 2, sf_date.strftime('%Y-%m-%d'), 50, "Production", "A", "US1", "FS1"),
        
        # Premix PS(A) - composant de base
        ManufacturingOrder("OF_PS_A_001", "PS_A", "PS_A", "PS", 1, ps_date.strftime('%Y-%m-%d'), 200, "Production", "A", "US1", "FS1"),
    ]
    
    # Nomenclature (BOM) - hiérarchie A
    bom_data = [
        # PF(A) contient SF(A)
        BOMEntry("PF_A", "SF_A", 2.0, 2),  # 1 PF(A) nécessite 2 SF(A)
        
        # SF(A) contient PS(A)  
        BOMEntry("SF_A", "PS_A", 4.0, 1),  # 1 SF(A) nécessite 4 PS(A)
    ]
    
    print(f"Input OFs:")
    for of in ofs:
        print(f"  {of}")
    
    print(f"\nBOM Structure:")
    for bom in bom_data:
        print(f"  {bom.parent_product_id} → {bom.child_product_id} (qty: {bom.quantity_child_per_parent})")
    
    # Exécuter l'algorithme de groupement
    groups, _ = run_grouping_algorithm(ofs, bom_data, horizon_H_weeks_param=4)
    
    print(f"\n=== Résultats du groupement ===")
    print(f"Nombre de groupes créés: {len(groups)}")
    
    for group in groups:
        print(f"\nGroupe {group.id}:")
        print(f"  PS principal: {group.ps_product_id}")
        print(f"  Fenêtre: {group.time_window_start.strftime('%Y-%m-%d')} → {group.time_window_end.strftime('%Y-%m-%d')}")
        print(f"  OFs dans le groupe:")
        
        # Trier les OFs par niveau BOM pour afficher la hiérarchie
        group_ofs = sorted(group.ofs, key=lambda x: x.bom_level)
        for of in group_ofs:
            print(f"    - {of.product_type}({of.product_id}) - {of.need_date.strftime('%Y-%m-%d')} - Niveau BOM: {of.bom_level}")
        
        print(f"  Stocks de composants:")
        for comp_id, stock in group.component_stocks.items():
            print(f"    - {comp_id}: {stock}")
    
    # Validation du concept
    validation_passed = True
    validation_messages = []
    
    if len(groups) != 1:
        validation_passed = False
        validation_messages.append(f"❌ Attendu 1 groupe, obtenu {len(groups)}")
    else:
        group = groups[0]
        
        # Vérifier que tous les niveaux sont présents
        product_types_in_group = {of.product_type for of in group.ofs}
        expected_types = {"PS", "SF", "PF"}
        
        if product_types_in_group == expected_types:
            validation_messages.append("✅ Tous les niveaux de produits sont groupés ensemble (PS, SF, PF)")
        else:
            validation_passed = False
            validation_messages.append(f"❌ Types manquants: {expected_types - product_types_in_group}")
        
        # Vérifier que la fenêtre est basée sur PS
        expected_window_start = datetime(2024, 1, 15)  # Lundi de la semaine PS
        if group.time_window_start.date() == expected_window_start.date():
            validation_messages.append("✅ Fenêtre temporelle basée sur la date PS")
        else:
            validation_passed = False
            validation_messages.append(f"❌ Fenêtre incorrecte: {group.time_window_start} vs attendu {expected_window_start}")
        
        # Vérifier la hiérarchie des produits
        family_products = {of.product_id for of in group.ofs if of.product_id.endswith("_A")}
        expected_family = {"PS_A", "SF_A", "PF_A"}
        
        if family_products == expected_family:
            validation_messages.append("✅ Toute la famille A est groupée ensemble")
        else:
            validation_passed = False
            validation_messages.append(f"❌ Famille incomplète: {family_products} vs {expected_family}")
    
    print(f"\n=== Validation du concept ===")
    for msg in validation_messages:
        print(f"  {msg}")
    
    if validation_passed:
        print(f"\n🎉 SUCCESS: L'algorithme respecte parfaitement le concept du diagramme !")
        return True
    else:
        print(f"\n❌ ÉCHEC: L'algorithme ne respecte pas entièrement le concept.")
        return False

def test_multiple_families():
    """
    Test avec plusieurs familles pour vérifier la séparation correcte
    """
    print("\n=== Test avec plusieurs familles ===")
    
    base_date = datetime(2024, 1, 15)  # Lundi
    
    # Famille A
    ofs_a = [
        ManufacturingOrder("OF_PF_A_001", "PF_A", "PF_A", "PF", 3, (base_date + timedelta(days=3)).strftime('%Y-%m-%d'), 100, "Client", "A", "US1", "FS1"),
        ManufacturingOrder("OF_SF_A_001", "SF_A", "SF_A", "SF", 2, (base_date + timedelta(days=2)).strftime('%Y-%m-%d'), 50, "Production", "A", "US1", "FS1"),
        ManufacturingOrder("OF_PS_A_001", "PS_A", "PS_A", "PS", 1, (base_date + timedelta(days=1)).strftime('%Y-%m-%d'), 200, "Production", "A", "US1", "FS1"),
    ]
    
    # Famille B (semaine suivante)
    ofs_b = [
        ManufacturingOrder("OF_PF_B_001", "PF_B", "PF_B", "PF", 3, (base_date + timedelta(days=10)).strftime('%Y-%m-%d'), 150, "Client", "B", "US1", "FS1"),
        ManufacturingOrder("OF_SF_B_001", "SF_B", "SF_B", "SF", 2, (base_date + timedelta(days=9)).strftime('%Y-%m-%d'), 75, "Production", "B", "US1", "FS1"),
        ManufacturingOrder("OF_PS_B_001", "PS_B", "PS_B", "PS", 1, (base_date + timedelta(days=8)).strftime('%Y-%m-%d'), 300, "Production", "B", "US1", "FS1"),
    ]
    
    all_ofs = ofs_a + ofs_b
    
    # BOM pour les deux familles
    bom_data = [
        # Famille A
        BOMEntry("PF_A", "SF_A", 2.0, 2),
        BOMEntry("SF_A", "PS_A", 4.0, 1),
        
        # Famille B
        BOMEntry("PF_B", "SF_B", 1.5, 2), 
        BOMEntry("SF_B", "PS_B", 3.0, 1),
    ]
    
    groups, _ = run_grouping_algorithm(all_ofs, bom_data, horizon_H_weeks_param=4)
    
    print(f"Nombre de groupes créés: {len(groups)}")
    
    family_a_group = None
    family_b_group = None
    
    for group in groups:
        family_ids = {of.product_id.split("_")[1] for of in group.ofs if "_" in of.product_id}
        if "A" in family_ids:
            family_a_group = group
        if "B" in family_ids:
            family_b_group = group
        
        print(f"\nGroupe {group.id}: Familles {family_ids}")
        for of in sorted(group.ofs, key=lambda x: x.bom_level):
            print(f"  - {of.product_type}({of.product_id}) - {of.need_date.strftime('%Y-%m-%d')}")
    
    # Validation
    if len(groups) == 2 and family_a_group and family_b_group:
        print(f"\n✅ SUCCESS: Les familles A et B sont correctement séparées en 2 groupes distincts")
        return True
    else:
        print(f"\n❌ ÉCHEC: Séparation incorrecte des familles")
        return False

if __name__ == "__main__":
    print("Test de validation du concept Sothemalgo")
    print("=" * 50)
    
    success1 = test_concept_validation()
    success2 = test_multiple_families()
    
    print(f"\n" + "=" * 50)
    if success1 and success2:
        print("🎉 TOUS LES TESTS PASSENT - Le concept est correctement implémenté !")
    else:
        print("❌ Certains tests échouent - Vérification nécessaire")
