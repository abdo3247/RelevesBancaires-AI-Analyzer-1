import unittest
from datetime import datetime
from decimal import Decimal
import pandas as pd
from src.analysis import parse_period, analyze_continuity, merge_statements, ConsistencyReport

class TestAnalysis(unittest.TestCase):
    def test_parse_period(self):
        self.assertEqual(parse_period("01/2024"), datetime(2024, 1, 1))
        self.assertEqual(parse_period("Janvier 2024"), datetime(2024, 1, 1))
        self.assertEqual(parse_period("février 2024"), datetime(2024, 2, 1))
        
    def test_consistency_check(self):
        r1 = {
            'periode': '01/2024', 
            'solde_final': 1000.00,
            'titulaire': 'Test',
            'banque': 'AWB'
        }
        r2 = {
            'periode': '02/2024', 
            'solde_initial': 1000.00, # Matches r1 final
            'solde_final': 1500.00,
            'titulaire': 'Test',
            'banque': 'AWB'
        }
        r3 = {
            'periode': '03/2024', 
            'solde_initial': 1400.00, # Mismatch with r2 final (1500)
            'solde_final': 2000.00,
            'titulaire': 'Test',
            'banque': 'AWB'
        }
        
        reports = analyze_continuity([r3, r1, r2]) # Intentionally unordered
        
        # Should be ordered 01 -> 02 -> 03
        self.assertEqual(len(reports), 2)
        
        # Report 1: Jan -> Feb (Consistent)
        self.assertTrue(reports[0].is_consistent)
        self.assertTrue(reports[0].is_consecutive)
        
        # Report 2: Feb -> Mar (Inconsistent)
        self.assertFalse(reports[1].is_consistent)
        self.assertEqual(reports[1].gap, Decimal('1400.00') - Decimal('1500.00'))

    def test_merge_statements(self):
        tx1 = [{'date': '2024-01-05', 'amount': 100}, {'date': '2024-01-01', 'amount': 50}]
        tx2 = [{'date': '2024-02-15', 'amount': 200}]
        
        df = merge_statements([tx1, tx2])
        
        self.assertEqual(len(df), 3)
        # Check sorting: 01-01, then 01-05, then 02-15
        self.assertEqual(df.iloc[0]['amount'], 50)
        self.assertEqual(df.iloc[2]['amount'], 200)

if __name__ == '__main__':
    unittest.main()
