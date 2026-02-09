"""
Test script for Job Application System
Run this to verify the system is properly configured
"""
import sys
import os

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

def test_imports():
    """Test that all modules can be imported"""
    print("Testing imports...")
    try:
        from utils.database import DatabaseManager
        from utils.config import get_config
        from utils.logging_utils import setup_logging
        from utils.anti_detection import AntiDetectionManager
        print("✓ Utils imports successful")
    except Exception as e:
        print(f"✗ Utils import failed: {e}")
        return False
    
    try:
        from agents.scraping_agent import ScrapingAgent
        from agents.analysis_agent import AnalysisAgent
        from agents.cover_letter_agent import CoverLetterAgent
        from agents.application_agent import ApplicationAgent
        print("✓ Agent imports successful")
    except Exception as e:
        print(f"✗ Agent import failed: {e}")
        return False
    
    try:
        from orchestrator import JobApplicationOrchestrator
        print("✓ Orchestrator import successful")
    except Exception as e:
        print(f"✗ Orchestrator import failed: {e}")
        return False
    
    return True

def test_database():
    """Test database initialization"""
    print("\nTesting database...")
    try:
        from utils.database import DatabaseManager
        db = DatabaseManager()
        
        # Test basic operations
        with db._get_connection() as conn:
            cursor = conn.execute("SELECT 1")
            assert cursor.fetchone()[0] == 1
        
        print("✓ Database initialization successful")
        return True
    except Exception as e:
        print(f"✗ Database test failed: {e}")
        return False

def test_config():
    """Test configuration loading"""
    print("\nTesting configuration...")
    try:
        from utils.config import get_config
        config = get_config()
        
        # Test basic config access
        user = config.get_user_profile()
        assert 'full_name' in user
        
        platforms = config.get_enabled_platforms()
        assert isinstance(platforms, list)
        
        print("✓ Configuration loading successful")
        print(f"  - User: {user.get('full_name', 'N/A')}")
        print(f"  - Enabled platforms: {', '.join(platforms) if platforms else 'None'}")
        return True
    except Exception as e:
        print(f"✗ Configuration test failed: {e}")
        return False

def test_agents():
    """Test agent initialization"""
    print("\nTesting agents...")
    try:
        from utils.database import DatabaseManager
        from agents.scraping_agent import ScrapingAgent
        from agents.analysis_agent import AnalysisAgent
        from agents.cover_letter_agent import CoverLetterAgent
        from agents.application_agent import ApplicationAgent
        
        db = DatabaseManager()
        
        # Test agent initialization (don't run them)
        scraping = ScrapingAgent(db)
        analysis = AnalysisAgent(db)
        cover = CoverLetterAgent(db)
        application = ApplicationAgent(db)
        
        print("✓ All agents initialized successfully")
        return True
    except Exception as e:
        print(f"✗ Agent test failed: {e}")
        return False

def test_dashboard():
    """Test dashboard Flask app"""
    print("\nTesting dashboard...")
    try:
        from dashboard.app import app
        
        # Test Flask app
        with app.test_client() as client:
            response = client.get('/')
            assert response.status_code == 200
        
        print("✓ Dashboard app initialized successfully")
        return True
    except Exception as e:
        print(f"✗ Dashboard test failed: {e}")
        return False

def test_templates():
    """Test that templates exist"""
    print("\nTesting templates...")
    try:
        from pathlib import Path
        
        templates = [
            'documents/templates/cover_letter_fr_template.txt',
            'documents/templates/cover_letter_en_template.txt',
            'dashboard/templates/index.html',
            'dashboard/static/css/styles.css',
            'dashboard/static/js/dashboard.js'
        ]
        
        all_exist = True
        for template in templates:
            path = Path(template)
            if path.exists():
                print(f"  ✓ {template}")
            else:
                print(f"  ✗ {template} NOT FOUND")
                all_exist = False
        
        return all_exist
    except Exception as e:
        print(f"✗ Template test failed: {e}")
        return False

def main():
    """Run all tests"""
    print("="*60)
    print("Job Application System - Test Suite")
    print("="*60)
    
    tests = [
        ("Imports", test_imports),
        ("Database", test_database),
        ("Configuration", test_config),
        ("Agents", test_agents),
        ("Dashboard", test_dashboard),
        ("Templates", test_templates)
    ]
    
    results = []
    for name, test_func in tests:
        try:
            result = test_func()
            results.append((name, result))
        except Exception as e:
            print(f"\n✗ {name} test crashed: {e}")
            results.append((name, False))
    
    print("\n" + "="*60)
    print("Test Summary")
    print("="*60)
    
    passed = sum(1 for _, r in results if r)
    total = len(results)
    
    for name, result in results:
        status = "✓ PASS" if result else "✗ FAIL"
        print(f"{status}: {name}")
    
    print(f"\nTotal: {passed}/{total} tests passed")
    
    if passed == total:
        print("\n🎉 All tests passed! System is ready to use.")
        return 0
    else:
        print(f"\n⚠️  {total - passed} test(s) failed. Please check the errors above.")
        return 1

if __name__ == "__main__":
    sys.exit(main())
