"""Attempt distance allocation includes blocked kicks, with source accounting."""
import unittest
from fr.generate import attempts_by_distance,FG_ATTEMPTS

class DistanceTests(unittest.TestCase):
    def test_blocked_attempts_use_their_own_distance_bucket(self):
        row=dict(player_id='test',fg_made_list='19;29;30;49;50;65',fg_made='6',
                 fg_missed_list='39;50',fg_missed='2',fg_blocked_list='29;40',fg_blocked='2',fg_att='10')
        self.assertEqual(list(attempts_by_distance(row).values()),[3,2,2,3])
        row['fg_blocked']='1'
        with self.assertRaises(AssertionError):attempts_by_distance(row)


if __name__ == "__main__":
    unittest.main()
