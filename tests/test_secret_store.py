import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from cryptography.fernet import Fernet

from backend.app.secret_store import decrypt_secret, encrypt_secret, secret_hint


class SecretStoreTests(unittest.TestCase):
    def test_cifra_e_decifra_sem_expor_texto_original(self):
        with tempfile.TemporaryDirectory() as diretorio:
            caminho = str(Path(diretorio) / "master.key")
            with patch.dict(
                os.environ,
                {"AI_LOCAL_MASTER_KEY_PATH": caminho},
                clear=False,
            ):
                segredo = "api-key-confidencial-1234"
                cifrado = encrypt_secret(segredo)

                self.assertNotIn(segredo, cifrado)
                self.assertEqual(decrypt_secret(cifrado), segredo)
                self.assertEqual(secret_hint(segredo), "••••1234")
                self.assertTrue(Path(caminho).exists())

    def test_chave_mestra_diferente_nao_decifra(self):
        with tempfile.TemporaryDirectory() as diretorio:
            caminho = str(Path(diretorio) / "master.key")
            with patch.dict(
                os.environ,
                {"AI_LOCAL_MASTER_KEY_PATH": caminho},
                clear=False,
            ):
                cifrado = encrypt_secret("segredo")
                Path(caminho).write_bytes(Fernet.generate_key())
                with self.assertRaisesRegex(RuntimeError, "Não foi possível decifrar"):
                    decrypt_secret(cifrado)

    def test_chave_nao_pode_ser_vazia(self):
        with self.assertRaisesRegex(ValueError, "não pode ficar vazia"):
            encrypt_secret("  ")


if __name__ == "__main__":
    unittest.main()
