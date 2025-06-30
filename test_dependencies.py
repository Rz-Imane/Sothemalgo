#!/usr/bin/env python3
"""
Script de validation des dépendances Sothemalgo
Teste que toutes les dépendances nécessaires sont installées et fonctionnelles
"""

import sys

def test_minimal_dependencies():
    """Teste les dépendances minimales pour l'algorithme"""
    print("🧪 Test des dépendances minimales...")
    
    try:
        import numpy
        print(f"  ✅ numpy {numpy.__version__}")
    except ImportError:
        print("  ❌ numpy manquant")
        return False
    
    try:
        import pandas
        print(f"  ✅ pandas {pandas.__version__}")
    except ImportError:
        print("  ❌ pandas manquant")
        return False
        
    try:
        import dateutil
        print(f"  ✅ python-dateutil {dateutil.__version__}")
    except ImportError:
        print("  ❌ python-dateutil manquant")
        return False
        
    try:
        import pytz
        print(f"  ✅ pytz {pytz.__version__}")
    except ImportError:
        print("  ❌ pytz manquant")
        return False
    
    return True

def test_web_dependencies():
    """Teste les dépendances pour l'interface web"""
    print("🌐 Test des dépendances web...")
    
    try:
        import flask
        # Flask dépréciera __version__, utilisons importlib si disponible
        try:
            from importlib.metadata import version
            flask_version = version('flask')
        except ImportError:
            try:
                flask_version = flask.__version__
            except AttributeError:
                flask_version = "version inconnue"
        print(f"  ✅ Flask {flask_version}")
    except ImportError:
        print("  ❌ Flask manquant")
        return False
        
    try:
        import waitress
        # Waitress n'a pas d'attribut __version__, utilisons importlib
        try:
            from importlib.metadata import version
            waitress_version = version('waitress')
        except ImportError:
            waitress_version = "version inconnue"
        print(f"  ✅ waitress {waitress_version}")
    except ImportError:
        print("  ❌ waitress manquant")
        return False
    
    return True

def test_algorithm():
    """Teste que l'algorithme peut être importé"""
    print("🔧 Test de l'algorithme...")
    
    try:
        import sothemalgo_grouper
        print("  ✅ sothemalgo_grouper importé avec succès")
        return True
    except ImportError as e:
        print(f"  ❌ Erreur import sothemalgo_grouper: {e}")
        return False

def main():
    """Fonction principale de test"""
    print("=" * 50)
    print("🏭 VALIDATION DÉPENDANCES SOTHEMALGO")
    print("=" * 50)
    
    minimal_ok = test_minimal_dependencies()
    web_ok = test_web_dependencies()
    algo_ok = test_algorithm()
    
    print("\n" + "=" * 50)
    print("📋 RÉSUMÉ")
    print("=" * 50)
    
    if minimal_ok:
        print("✅ Dépendances minimales : OK")
        print("   Vous pouvez utiliser l'algorithme en ligne de commande")
    else:
        print("❌ Dépendances minimales : ÉCHEC")
        print("   Installez avec : pip install -r requirements-minimal.txt")
    
    if web_ok:
        print("✅ Dépendances web : OK")
        print("   Vous pouvez lancer l'interface web")
    else:
        print("❌ Dépendances web : ÉCHEC")
        print("   Installez avec : pip install -r requirements.txt")
    
    if algo_ok:
        print("✅ Algorithme : OK")
        print("   Tous les modules sont accessibles")
    else:
        print("❌ Algorithme : ÉCHEC")
        print("   Vérifiez que vous êtes dans le bon répertoire")
    
    print("\n💡 PROCHAINES ÉTAPES :")
    if minimal_ok and algo_ok:
        print("   - Tester l'algorithme : python test_new_algo.py")
    if web_ok and algo_ok:
        print("   - Lancer l'interface web : python sothemalgo_web.py")
        print("   - Accéder à l'interface : http://localhost:5002")
    
    # Code de retour
    if minimal_ok and algo_ok:
        return 0
    else:
        return 1

if __name__ == "__main__":
    sys.exit(main())
