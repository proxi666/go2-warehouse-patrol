"""CPU-only prompt provenance gates; snapshot Python is never executed."""
import hashlib
import importlib.util
from pathlib import Path
import unittest

SCRIPT = Path(__file__).resolve().parents[1] / 'scripts/verify_attempt.py'
spec = importlib.util.spec_from_file_location('verify_attempt', SCRIPT)
verifier = importlib.util.module_from_spec(spec)
spec.loader.exec_module(verifier)


class PromptIdentityTests(unittest.TestCase):
    def setUp(self):
        self.source = "raise RuntimeError('must not execute')\nPROMPT = 'historical prompt'\n"
        self.health = {'prompt_sha256':hashlib.sha256(b'historical prompt').hexdigest(),
                       'source_sha256':{key:'a'*64 for key in
                         ('scripts/cosmos_server.py','src/warehouse_incident/cosmos.py','src/warehouse_incident/core.py')}}
        self.record = {**self.health}

    def test_historical_snapshot_independent_of_current_prompt(self):
        self.assertEqual(verifier.prompt_identity(self.source,self.health,self.record),self.health['prompt_sha256'])

    def test_corrupt_request_prompt_rejected(self):
        self.record['prompt_sha256'] = '0'*64
        with self.assertRaisesRegex(verifier.VerificationFailure,'Request prompt'):
            verifier.prompt_identity(self.source,self.health,self.record)

    def test_corrupt_health_prompt_rejected(self):
        self.health['prompt_sha256'] = '0'*64
        with self.assertRaisesRegex(verifier.VerificationFailure,'health prompt'):
            verifier.prompt_identity(self.source,self.health)

    def test_missing_prompt_identity_rejected(self):
        self.record.pop('prompt_sha256')
        with self.assertRaises(verifier.VerificationFailure):
            verifier.prompt_identity(self.source,self.health,self.record)

    def test_service_changed_between_health_and_request_rejected(self):
        self.record['source_sha256'] = {**self.health['source_sha256'],'scripts/cosmos_server.py':'b'*64}
        with self.assertRaisesRegex(verifier.VerificationFailure,'service source'):
            verifier.prompt_identity(self.source,self.health,self.record)

    def test_dynamic_prompt_not_executed(self):
        with self.assertRaisesRegex(verifier.VerificationFailure,'literal'):
            verifier.prompt_identity("PROMPT = str('historical prompt')",self.health)

    def test_missing_service_source_identity_rejected(self):
        self.health.pop('source_sha256')
        with self.assertRaisesRegex(verifier.VerificationFailure,'source SHA256'):
            verifier.prompt_identity(self.source,self.health)

    def test_unknown_prompt_name_rejected(self):
        self.health['prompt_name'] = '__import__'
        with self.assertRaisesRegex(verifier.VerificationFailure, 'unknown or inconsistent'):
            verifier.prompt_identity(self.source,self.health)

    def test_mislabeled_task_rejected(self):
        for task,name in [('patrol','PROMPT'),('incident','PATROL_PROMPT'),('unknown','PROMPT')]:
            with self.subTest(task=task,name=name):
                with self.assertRaisesRegex(verifier.VerificationFailure, 'unknown or inconsistent'):
                    verifier.prompt_identity(self.source,{**self.health,'task':task,'prompt_name':name})

    def test_patrol_selects_rack_literal_not_legacy_prompt(self):
        source = self.source + "PATROL_PROMPT = 'rack-specific prompt'\nPATROL_SYSTEM = 'fixture system'\n"
        health = {**self.health,'task':'patrol','prompt_name':'PATROL_PROMPT',
                  'system_prompt_name':'PATROL_SYSTEM','system_prompt_sha256':hashlib.sha256(b'fixture system').hexdigest(),
                  'prompt_sha256':hashlib.sha256(b'rack-specific prompt').hexdigest()}
        self.assertEqual(verifier.prompt_identity(source,health,dict(health)),health['prompt_sha256'])
        with self.assertRaisesRegex(verifier.VerificationFailure, 'health prompt'):
            verifier.prompt_identity(source,{**health,'prompt_sha256':self.health['prompt_sha256']})

    def test_record_prompt_name_mismatch_rejected_even_with_same_hash(self):
        record = {**self.record,'task':'patrol','prompt_name':'PATROL_PROMPT'}
        with self.assertRaisesRegex(verifier.VerificationFailure, 'Request task/prompt_name'):
            verifier.prompt_identity(self.source,self.health,record)

    def test_explicit_incident_identity_accepts_legacy_record(self):
        health = {**self.health,'task':'incident','prompt_name':'PROMPT'}
        self.assertEqual(verifier.prompt_identity(self.source,health,self.record),health['prompt_sha256'])

    def test_patrol_system_hash_required_and_bound_to_literal(self):
        source = self.source + "PATROL_PROMPT = 'rack'\nPATROL_SYSTEM = 'system'\n"
        health = {**self.health,'task':'patrol','prompt_name':'PATROL_PROMPT',
                  'prompt_sha256':hashlib.sha256(b'rack').hexdigest(),'system_prompt_name':'PATROL_SYSTEM',
                  'system_prompt_sha256':hashlib.sha256(b'system').hexdigest()}
        self.assertEqual(verifier.prompt_identity(source,health,dict(health)),health['prompt_sha256'])
        for change in ({'system_prompt_sha256':None},{'system_prompt_sha256':'0'*64},
                       {'system_prompt_name':'OTHER'}):
            with self.subTest(change=change), self.assertRaises(verifier.VerificationFailure):
                verifier.prompt_identity(source,{**health,**change})
        for change in ({'system_prompt_sha256':None},{'system_prompt_sha256':'0'*64},
                       {'system_prompt_name':'OTHER'}):
            with self.subTest(record=change), self.assertRaisesRegex(verifier.VerificationFailure,'Request system'):
                verifier.prompt_identity(source,health,{**health,**change})

    def test_incident_cannot_claim_patrol_system(self):
        with self.assertRaisesRegex(verifier.VerificationFailure,'Incident task'):
            verifier.prompt_identity(self.source,{**self.health,'system_prompt_name':'PATROL_SYSTEM'})
