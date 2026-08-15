import os
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path

from dotenv import load_dotenv


PROVIDER_GOOGLE_GEMINI = "google_gemini"
DEFAULT_GENERATION_MODEL = "gemini-2.5-flash"
DEFAULT_EMBEDDING_MODEL = "gemini-embedding-001"
CURRENT_VECTOR_DIMENSIONS = 768

TASK_FORMULATION = "formulation"
TASK_SCREENING = "screening"
TASK_RAG = "rag"
TASK_RERANKING = "reranking"
TASK_EVALUATION = "evaluation"
TASK_EXTRACTION = "extraction"
TASK_REPORT = "report"

GENERATION_TASKS = (
    TASK_FORMULATION,
    TASK_SCREENING,
    TASK_RAG,
    TASK_RERANKING,
    TASK_EVALUATION,
    TASK_EXTRACTION,
    TASK_REPORT,
)

TASK_MODEL_ENV = {
    TASK_FORMULATION: "AI_FORMULATION_MODEL",
    TASK_SCREENING: "AI_SCREENING_MODEL",
    TASK_RAG: "AI_RAG_MODEL",
    TASK_RERANKING: "AI_RERANKING_MODEL",
    TASK_EVALUATION: "AI_EVALUATION_MODEL",
    TASK_EXTRACTION: "AI_EXTRACTION_MODEL",
    TASK_REPORT: "AI_REPORT_MODEL",
}
TASK_TEMPERATURE_ENV = {
    TASK_FORMULATION: "AI_FORMULATION_TEMPERATURE",
    TASK_SCREENING: "AI_SCREENING_TEMPERATURE",
    TASK_RAG: "AI_RAG_TEMPERATURE",
    TASK_RERANKING: "AI_RERANKING_TEMPERATURE",
    TASK_EVALUATION: "AI_EVALUATION_TEMPERATURE",
    TASK_EXTRACTION: "AI_EXTRACTION_TEMPERATURE",
    TASK_REPORT: "AI_REPORT_TEMPERATURE",
}
TASK_DEFAULT_TEMPERATURE = {
    TASK_FORMULATION: 0.2,
    TASK_SCREENING: 0.0,
    TASK_RAG: 0.1,
    TASK_RERANKING: 0.0,
    TASK_EVALUATION: 0.0,
    TASK_EXTRACTION: 0.0,
    TASK_REPORT: 0.2,
}


def load_project_environment():
    """Carrega configurações locais conhecidas sem sobrescrever o ambiente do SO."""
    backend_dir = Path(__file__).resolve().parents[1]
    project_root = backend_dir.parent
    for env_path in (project_root / ".env", backend_dir / ".env"):
        if env_path.exists():
            load_dotenv(env_path, override=False)


load_project_environment()


def _normalizar_provider(valor):
    aliases = {
        "google": PROVIDER_GOOGLE_GEMINI,
        "gemini": PROVIDER_GOOGLE_GEMINI,
        "google_gemini": PROVIDER_GOOGLE_GEMINI,
    }
    normalizado = str(valor or PROVIDER_GOOGLE_GEMINI).strip().lower()
    return aliases.get(normalizado, normalizado)


def _ler_inteiro(nome, padrao):
    try:
        valor = int(os.getenv(nome, str(padrao)))
    except ValueError as erro:
        raise RuntimeError(f"{nome} deve ser um número inteiro.") from erro
    if valor <= 0:
        raise RuntimeError(f"{nome} deve ser maior que zero.")
    return valor


def _ler_temperatura(nome, padrao):
    valor = os.getenv(nome)
    if valor is None or not valor.strip():
        return padrao
    if valor.strip().lower() in {"none", "null", "disabled", "off"}:
        return None
    try:
        temperatura = float(valor)
    except ValueError as erro:
        raise RuntimeError(f"{nome} deve ser um número ou 'none'.") from erro
    if not 0 <= temperatura <= 2:
        raise RuntimeError(f"{nome} deve estar entre 0 e 2.")
    return temperatura


def _ler_peso(nome, padrao):
    valor = os.getenv(nome)
    if valor is None or not valor.strip():
        return float(padrao)
    try:
        peso = float(valor)
    except ValueError as erro:
        raise RuntimeError(f"{nome} deve ser um número entre 0 e 1.") from erro
    if not 0 <= peso <= 1:
        raise RuntimeError(f"{nome} deve estar entre 0 e 1.")
    return peso


def _ler_booleano(nome, padrao):
    valor = os.getenv(nome)
    if valor is None or not valor.strip():
        return bool(padrao)
    normalizado = valor.strip().lower()
    if normalizado in {"1", "true", "yes", "on", "sim"}:
        return True
    if normalizado in {"0", "false", "no", "off", "nao", "não"}:
        return False
    raise RuntimeError(f"{nome} deve ser verdadeiro ou falso.")


def _inteiro_configuracao(valor, padrao, nome):
    if valor in (None, ""):
        return int(padrao)
    try:
        resultado = int(valor)
    except (TypeError, ValueError) as erro:
        raise RuntimeError(f"{nome} deve ser um número inteiro.") from erro
    if resultado <= 0:
        raise RuntimeError(f"{nome} deve ser maior que zero.")
    return resultado


def _peso_configuracao(valor, padrao, nome):
    if valor in (None, ""):
        return float(padrao)
    try:
        peso = float(valor)
    except (TypeError, ValueError) as erro:
        raise RuntimeError(f"{nome} deve ser um número entre 0 e 1.") from erro
    if not 0 <= peso <= 1:
        raise RuntimeError(f"{nome} deve estar entre 0 e 1.")
    return peso


def _booleano_configuracao(valor, padrao):
    if valor is None:
        return bool(padrao)
    if isinstance(valor, bool):
        return valor
    normalizado = str(valor).strip().lower()
    if normalizado in {"1", "true", "yes", "on", "sim"}:
        return True
    if normalizado in {"0", "false", "no", "off", "nao", "não"}:
        return False
    return bool(padrao)


def model_supports_sampling_parameters(provider, model):
    """Evita enviar parâmetros removidos por modelos Gemini mais recentes."""
    if provider != PROVIDER_GOOGLE_GEMINI:
        return True
    modelo = str(model).lower()
    sem_amostragem = (
        "gemini-3.5-",
        "gemini-3.6-",
    )
    return not (modelo.startswith(sem_amostragem) or modelo == "gemini-flash-latest")


@dataclass(frozen=True)
class GenerationTaskConfig:
    task: str
    provider: str
    model: str
    temperature: float | None
    source: str = "environment"
    enabled: bool = True
    candidate_limit: int | None = None
    final_limit: int | None = None
    rrf_weight: float | None = None

    @property
    def effective_temperature(self):
        if not model_supports_sampling_parameters(self.provider, self.model):
            return None
        return self.temperature

    def metadata(self):
        metadata = {
            "provider": self.provider,
            "model_name": self.model,
            "temperature": self.effective_temperature,
            "configuration_source": self.source,
            "task": self.task,
        }
        if self.task == TASK_RERANKING:
            metadata["enabled"] = self.enabled
            metadata["candidate_limit"] = self.candidate_limit
            metadata["final_limit"] = self.final_limit
            metadata["rrf_weight"] = self.rrf_weight
        return metadata


@dataclass(frozen=True)
class EmbeddingConfig:
    provider: str
    model: str
    dimensions: int
    source: str = "environment"

    def metadata(self):
        return {
            "provider": self.provider,
            "model_name": self.model,
            "dimensions": self.dimensions,
            "configuration_source": self.source,
            "task": "embedding",
        }


@dataclass(frozen=True)
class AISettings:
    provider: str
    api_key: str | None = field(repr=False)
    generation: dict[str, GenerationTaskConfig]
    embedding: EmbeddingConfig
    credential_id: str | None = None
    credential_source: str = "environment"


def _database_configuration_enabled():
    return os.getenv("AI_CONFIG_DATABASE_ENABLED", "true").strip().lower() not in {
        "0", "false", "no", "off",
    }


def _apply_database_overrides(settings):
    """Aplica o escopo local da instalação, mantendo .env como fallback seguro."""
    if not _database_configuration_enabled():
        return settings

    try:
        from backend.app.ai_config_repository import (
            configuration_tables_available,
            get_installation_credential,
            get_installation_model_settings,
        )

        if not configuration_tables_available():
            return settings
        modelos_banco = get_installation_model_settings()
        credencial = get_installation_credential()
    except Exception:
        # O aplicativo continua inicializável antes da migração ou se o banco estiver offline.
        return settings

    provider = settings.provider
    api_key = settings.api_key
    credential_id = None
    credential_source = "environment"
    if credencial:
        from backend.app.secret_store import decrypt_secret

        api_key = decrypt_secret(credencial["encrypted_secret"])
        provider = credencial["provider_code"]
        credential_id = str(credencial["id"])
        credential_source = "encrypted_database"

    geracao = {}
    for tarefa, configuracao in settings.generation.items():
        salvo = modelos_banco.get(tarefa)
        if not salvo:
            geracao[tarefa] = configuracao
            continue
        parametros = salvo.get("parameters_jsonb") or {}
        candidate_limit = configuracao.candidate_limit
        final_limit = configuracao.final_limit
        rrf_weight = configuracao.rrf_weight
        enabled = configuracao.enabled
        if tarefa == TASK_RERANKING:
            candidate_limit = _inteiro_configuracao(
                parametros.get("candidate_limit"),
                configuracao.candidate_limit or 12,
                "candidate_limit",
            )
            final_limit = _inteiro_configuracao(
                parametros.get("final_limit"),
                configuracao.final_limit or 4,
                "final_limit",
            )
            if not 4 <= candidate_limit <= 30:
                raise RuntimeError("candidate_limit deve estar entre 4 e 30.")
            if not 2 <= final_limit <= 10:
                raise RuntimeError("final_limit deve estar entre 2 e 10.")
            if final_limit > candidate_limit:
                raise RuntimeError("O limite final do reranking não pode superar os candidatos.")
            rrf_weight = _peso_configuracao(
                parametros.get("rrf_weight"),
                configuracao.rrf_weight or 0.0,
                "rrf_weight",
            )
            enabled = _booleano_configuracao(parametros.get("enabled"), configuracao.enabled)
        geracao[tarefa] = GenerationTaskConfig(
            task=tarefa,
            provider=salvo["provider_code"],
            model=salvo["model_name"],
            temperature=parametros.get("temperature", configuracao.temperature),
            source="database",
            enabled=enabled,
            candidate_limit=candidate_limit,
            final_limit=final_limit,
            rrf_weight=rrf_weight,
        )

    embedding_salvo = modelos_banco.get("embedding")
    if embedding_salvo:
        embedding = EmbeddingConfig(
            provider=embedding_salvo["provider_code"],
            model=embedding_salvo["model_name"],
            dimensions=(
                embedding_salvo.get("embedding_dimensions")
                or settings.embedding.dimensions
            ),
            source="database",
        )
    else:
        embedding = settings.embedding

    return AISettings(
        provider=provider,
        api_key=api_key,
        generation=geracao,
        embedding=embedding,
        credential_id=credential_id,
        credential_source=credential_source,
    )


def get_environment_ai_settings():
    """Monta a configuração de fallback sem consultar credenciais persistidas."""
    provider = _normalizar_provider(os.getenv("AI_PROVIDER"))
    modelo_padrao = os.getenv(
        "AI_DEFAULT_GENERATION_MODEL",
        DEFAULT_GENERATION_MODEL,
    ).strip()
    if not modelo_padrao:
        raise RuntimeError("AI_DEFAULT_GENERATION_MODEL não pode ficar vazio.")

    geracao = {}
    for tarefa in GENERATION_TASKS:
        modelo = os.getenv(TASK_MODEL_ENV[tarefa], modelo_padrao).strip()
        if not modelo:
            raise RuntimeError(f"{TASK_MODEL_ENV[tarefa]} não pode ficar vazio.")
        candidate_limit = None
        final_limit = None
        rrf_weight = None
        enabled = True
        if tarefa == TASK_RERANKING:
            enabled = _ler_booleano("AI_RERANKING_ENABLED", True)
            candidate_limit = _ler_inteiro("AI_RERANKING_CANDIDATE_LIMIT", 12)
            final_limit = _ler_inteiro("AI_RERANKING_FINAL_LIMIT", 4)
            if not 4 <= candidate_limit <= 30:
                raise RuntimeError("AI_RERANKING_CANDIDATE_LIMIT deve estar entre 4 e 30.")
            if not 2 <= final_limit <= 10:
                raise RuntimeError("AI_RERANKING_FINAL_LIMIT deve estar entre 2 e 10.")
            if final_limit > candidate_limit:
                raise RuntimeError(
                    "AI_RERANKING_FINAL_LIMIT não pode superar AI_RERANKING_CANDIDATE_LIMIT."
                )
            rrf_weight = _ler_peso("AI_RERANKING_RRF_WEIGHT", 0.0)
        geracao[tarefa] = GenerationTaskConfig(
            task=tarefa,
            provider=provider,
            model=modelo,
            temperature=_ler_temperatura(
                TASK_TEMPERATURE_ENV[tarefa],
                TASK_DEFAULT_TEMPERATURE[tarefa],
            ),
            enabled=enabled,
            candidate_limit=candidate_limit,
            final_limit=final_limit,
            rrf_weight=rrf_weight,
        )

    embedding = EmbeddingConfig(
        provider=provider,
        model=os.getenv("AI_EMBEDDING_MODEL", DEFAULT_EMBEDDING_MODEL).strip(),
        dimensions=_ler_inteiro("AI_EMBEDDING_DIMENSIONS", CURRENT_VECTOR_DIMENSIONS),
    )
    if not embedding.model:
        raise RuntimeError("AI_EMBEDDING_MODEL não pode ficar vazio.")

    return AISettings(
        provider=provider,
        api_key=os.getenv("GEMINI_API_KEY"),
        generation=geracao,
        embedding=embedding,
    )


@lru_cache(maxsize=1)
def get_ai_settings():
    return _apply_database_overrides(get_environment_ai_settings())


def get_generation_config(task):
    try:
        return get_ai_settings().generation[task]
    except KeyError as erro:
        raise ValueError(f"Tarefa de IA desconhecida: {task}") from erro


def get_embedding_config():
    return get_ai_settings().embedding


def get_reranking_config():
    return get_generation_config(TASK_RERANKING)


def clear_ai_settings_cache():
    """Permite recarregar a configuração após mudanças futuras pela interface."""
    get_ai_settings.cache_clear()
