#!/usr/bin/env python3
# Script de test pour le nouvel algorithme

import sys
import os
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from sothemalgo_grouper import (
    load_ofs_from_file, load_bom_from_file, run_grouping_algorithm, 
    write_grouped_needs_to_file, load_posts_and_operations_data,
    smooth_and_schedule_groups
)

def test_new_algorithm():
    print("=== TESTING NEW ALGORITHM (PF/SF based) ===")
    
    try:
        # Charger les données
        ofs = load_ofs_from_file('test_besoins.csv')
        bom = load_bom_from_file('test_nomenclature.csv')
        posts_map, operations_map = load_posts_and_operations_data('test_posts.csv', 'post_unavailability.csv', 'test_operations.csv')
        
        print(f"Loaded {len(ofs)} OFs, {len(bom)} BOM entries")
        
        # Afficher les premiers OFs PF/SF
        pf_sf_ofs = [of for of in ofs if of.product_type in ["PF", "SF"]]
        print(f"Found {len(pf_sf_ofs)} PF/SF OFs:")
        for of in pf_sf_ofs[:5]:
            print(f"  {of.id}: {of.product_id} ({of.product_type}) - {of.need_date.strftime('%Y-%m-%d')}")
        
        # Test du nouveau grouping
        groups, ofs_updated = run_grouping_algorithm(ofs, bom, 4)
        print(f"\nSUCCESS: Created {len(groups)} groups")
        
        for group in groups:
            print(f"Group {group.id}: {len(group.ofs)} OFs, window: {group.time_window_start.strftime('%Y-%m-%d')} - {group.time_window_end.strftime('%Y-%m-%d')}")
            
        # Compter les OFs assignés
        assigned_ofs = [of for of in ofs_updated if of.assigned_group_id is not None]
        print(f"\nAssigned OFs: {len(assigned_ofs)}/{len(ofs_updated)}")
        
        # Planification détaillée
        params = {
            'advance_retreat_weeks': 3,
            'use_auto_mode': True
        }
        
        smooth_and_schedule_groups(groups, ofs_updated, bom, posts_map, operations_map, params)
        
        # Écrire le résultat
        write_grouped_needs_to_file('test_besoins_groupes_output_new.txt', groups, ofs_updated)
        print(f"\nOutput written to test_besoins_groupes_output_new.txt")
        
    except Exception as e:
        print(f"ERROR: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    test_new_algorithm()
