"""Explicit mapping of coaching preview names to live patch keys.

PROVED OFFLINE: the labels are authored in offensive_schemes.BUCKETS.
Native predicates and their limits are inventoried in apf_b76_a3.md.
"""
from .apf2k8_situation_mask import KEY_LABELS, situation_key


def bucket_key(bucket):
    return 12 if bucket.name == '2pt' else situation_key(bucket.situation())


def mapping_note(bucket):
    key = bucket_key(bucket)
    if key == 12:
        return ('Real game try phase 3. Edit Live situations: Two-point try. '
                'This candidate sample is a fourth-down scrimmage proxy, not a prediction '
                'of the native kick-versus-two-point decision. The policy applies only after '
                'the game requests ordinary offense; kicks retain their special path.')
    return (f'Studio sample label; Live situations sample maps to "{KEY_LABELS[key]}". '
            'No independent stored game row has this name. Other live downs/distances '
            'within this coaching label use their corresponding live bucket.')
