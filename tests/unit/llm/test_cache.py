import json
import logging

import pytest

from medroute.llm import (
    CachedClient,
    LLMError,
    MockClient,
    OpenAICompatibleClient,
    client_from_env,
    load_prompt,
)

SECRET = "gsk_segredo_de_teste"


class CountingClient:
    """Cliente falso com os parâmetros de um provedor real; conta as chamadas."""

    provider = "groq"
    model = "modelo-x"

    def __init__(self, temperature=0.2, max_tokens=1500, erro=None):
        self.temperature = temperature
        self.max_tokens = max_tokens
        self.erro = erro
        self.calls = 0

    def complete(self, system, user, *, prompt=None):
        self.calls += 1
        if self.erro:
            raise self.erro
        return f"resposta {self.calls} para {user}"


def entries(tmp_path):
    return sorted(tmp_path.glob("*.json"))


def test_mesma_entrada_chama_o_provedor_uma_vez(tmp_path):
    inner = CountingClient()
    client = CachedClient(inner, tmp_path)

    primeira = client.complete("sys", "usr")
    segunda = client.complete("sys", "usr")

    assert primeira == segunda == "resposta 1 para usr"
    assert inner.calls == 1
    assert (client.hits, client.misses) == (1, 1)
    assert len(entries(tmp_path)) == 1


def test_cache_sobrevive_a_um_novo_cliente(tmp_path):
    CachedClient(CountingClient(), tmp_path).complete("sys", "usr")
    inner = CountingClient()

    assert CachedClient(inner, tmp_path).complete("sys", "usr") == "resposta 1 para usr"
    assert inner.calls == 0


@pytest.mark.parametrize(
    "mudanca",
    [
        {"system": "outro"},
        {"user": "outro"},
        {"temperature": 0.9},
        {"max_tokens": 10},
        {"model": "modelo-y"},
        {"provider": "openai"},
    ],
)
def test_qualquer_campo_da_chave_diferente_gera_nova_chamada(tmp_path, mudanca):
    CachedClient(CountingClient(), tmp_path).complete("sys", "usr")

    inner = CountingClient(
        temperature=mudanca.get("temperature", 0.2), max_tokens=mudanca.get("max_tokens", 1500)
    )
    inner.model = mudanca.get("model", inner.model)
    inner.provider = mudanca.get("provider", inner.provider)
    CachedClient(inner, tmp_path).complete(mudanca.get("system", "sys"), mudanca.get("user", "usr"))

    assert inner.calls == 1
    assert len(entries(tmp_path)) == 2


def test_arquivo_registra_provedor_modelo_prompt_e_versao(tmp_path):
    prompt = load_prompt("instrucoes_motorista")
    CachedClient(CountingClient(), tmp_path).complete("sys", "olá, ação", prompt=prompt)

    (path,) = entries(tmp_path)
    entrada = json.loads(path.read_text(encoding="utf-8"))
    assert entrada["provider"] == "groq"
    assert entrada["model"] == "modelo-x"
    assert entrada["prompt"] == "instrucoes_motorista"
    assert entrada["versao"] == prompt.versao
    assert entrada["response"] == "resposta 1 para olá, ação"
    assert "olá, ação" in path.read_text(encoding="utf-8")  # acentos legíveis no arquivo


def test_arquivo_nao_contem_a_chave_de_api(tmp_path):
    env = {
        "LLM_PROVIDER": "groq",
        "GROQ_API_KEY": SECRET,
        "GROQ_MODEL": "modelo-x",
        "LLM_CACHE_DIR": str(tmp_path),
    }
    client = client_from_env(env)
    client.inner.complete = lambda system, user, *, prompt=None: "ok"  # sem rede

    assert client.complete("sys", "usr") == "ok"
    (path,) = entries(tmp_path)
    assert SECRET not in path.read_text(encoding="utf-8")


def test_erro_do_provedor_nao_e_gravado(tmp_path):
    client = CachedClient(CountingClient(erro=LLMError("falhou")), tmp_path)

    with pytest.raises(LLMError):
        client.complete("sys", "usr")
    assert list(tmp_path.iterdir()) == []


def test_arquivo_corrompido_e_refeito(tmp_path, caplog):
    inner = CountingClient()
    client = CachedClient(inner, tmp_path)
    client.complete("sys", "usr")
    (path,) = entries(tmp_path)
    path.write_text("{ não é json", encoding="utf-8")

    with caplog.at_level(logging.WARNING):
        assert client.complete("sys", "usr") == "resposta 2 para usr"
    assert "ilegível" in caplog.text
    assert json.loads(path.read_text(encoding="utf-8"))["response"] == "resposta 2 para usr"


def test_cria_o_diretorio_e_nao_deixa_temporarios(tmp_path):
    pasta = tmp_path / "data" / "cache" / "llm"
    CachedClient(CountingClient(), pasta).complete("sys", "usr")

    assert [p.suffix for p in pasta.iterdir()] == [".json"]


# --- client_from_env ---------------------------------------------------------


def test_provedor_real_com_cache_dir_usa_cache(tmp_path):
    env = {"LLM_PROVIDER": "openai", "OPENAI_API_KEY": SECRET, "OPENAI_MODEL": "m"}
    client = client_from_env({**env, "LLM_CACHE_DIR": str(tmp_path)})

    assert isinstance(client, CachedClient)
    assert isinstance(client.inner, OpenAICompatibleClient)
    assert (client.provider, client.model) == ("openai", "m")


@pytest.mark.parametrize("cache_dir", [None, "", "  "])
def test_provedor_real_sem_cache_dir_nao_usa_cache(cache_dir):
    env = {"LLM_PROVIDER": "openai", "OPENAI_API_KEY": SECRET, "OPENAI_MODEL": "m"}
    if cache_dir is not None:
        env["LLM_CACHE_DIR"] = cache_dir
    assert isinstance(client_from_env(env), OpenAICompatibleClient)


def test_mock_nunca_usa_cache(tmp_path):
    client = client_from_env({"LLM_PROVIDER": "mock", "LLM_CACHE_DIR": str(tmp_path)})
    assert isinstance(client, MockClient)
