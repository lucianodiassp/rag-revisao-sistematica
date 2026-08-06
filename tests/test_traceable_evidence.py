import unittest
from unittest.mock import Mock

from backend.agentes.agente_extrator import _salvar_extracao
from backend.app.evidence_utils import (
    NOT_REPORTED,
    achatar_extracao,
    listar_fontes_extracao,
    normalizar_trecho,
    validar_extracao_rastreavel,
)


class TraceableEvidenceTests(unittest.TestCase):
    def setUp(self):
        self.chunks = [
            {
                "id": "chunk-1",
                "page_number": 7,
                "chunk_text": "The proposed method achieved an accuracy of 94.2 percent.",
            },
            {
                "id": "chunk-2",
                "page_number": 9,
                "chunk_text": "A limitation is the small sample size used in this study.",
            },
        ]

    def test_normalizacao_preserva_validacao_com_quebras_de_linha(self):
        self.assertEqual(normalizar_trecho("A  B\nC"), "a b c")

    def test_citacao_literal_valida_recebe_pagina_do_banco(self):
        resposta = {
            "main_results": {
                "value": "Acurácia de 94,2%",
                "evidence": [
                    {
                        "chunk_id": "chunk-1",
                        "page": 999,
                        "quote": "achieved an accuracy of 94.2 percent",
                    }
                ],
                "confidence": 0.9,
            }
        }
        validada = validar_extracao_rastreavel(resposta, self.chunks)

        self.assertEqual(validada["main_results"]["evidence"][0]["page"], 7)
        self.assertEqual(validada["main_results"]["confidence"], 0.9)

    def test_valor_sem_citacao_literal_e_removido(self):
        resposta = {
            "objective": {
                "value": "Objetivo inventado",
                "evidence": [
                    {"chunk_id": "chunk-1", "quote": "This text does not exist"}
                ],
                "confidence": 1,
            }
        }
        validada = validar_extracao_rastreavel(resposta, self.chunks)

        self.assertEqual(validada["objective"]["value"], NOT_REPORTED)
        self.assertEqual(validada["objective"]["evidence"], [])
        self.assertTrue(validada["validation_warnings"])

    def test_chunk_desconhecido_e_descartado(self):
        resposta = {
            "limitations": {
                "value": ["Amostra pequena"],
                "evidence": [
                    {
                        "chunk_id": "outro-projeto",
                        "quote": "A limitation is the small sample size",
                    }
                ],
                "confidence": 0.8,
            }
        }
        validada = validar_extracao_rastreavel(resposta, self.chunks)
        self.assertEqual(validada["limitations"]["value"], [])

    def test_achatamento_e_listagem_de_fontes(self):
        resposta = {
            "metrics": {
                "value": ["Accuracy"],
                "evidence": [
                    {
                        "chunk_id": "chunk-1",
                        "quote": "accuracy of 94.2 percent",
                    }
                ],
                "confidence": 0.8,
            }
        }
        validada = validar_extracao_rastreavel(resposta, self.chunks)

        self.assertEqual(achatar_extracao(validada)["metrics"], ["Accuracy"])
        self.assertEqual(listar_fontes_extracao(validada)[0]["page_number"], 7)

    def test_persistencia_converte_uuid_python_para_texto(self):
        cursor = Mock()
        cursor.fetchone.return_value = None
        validada = validar_extracao_rastreavel(
            {
                "main_results": {
                    "value": "Acurácia de 94,2%",
                    "evidence": [
                        {
                            "chunk_id": "chunk-1",
                            "quote": "achieved an accuracy of 94.2 percent",
                        }
                    ],
                    "confidence": 0.9,
                }
            },
            self.chunks,
        )

        extracao_id = _salvar_extracao(cursor, "project-1", "paper-1", validada)

        self.assertIsInstance(extracao_id, str)
        parametros_insert = cursor.execute.call_args_list[1].args[1]
        self.assertIsInstance(parametros_insert[0], str)


if __name__ == "__main__":
    unittest.main()
