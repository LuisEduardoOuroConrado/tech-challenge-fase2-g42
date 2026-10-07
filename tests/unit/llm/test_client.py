from types import SimpleNamespace

import httpx
import openai
import pytest

from medroute.llm import LLMError, MockClient, OpenAICompatibleClient, client_from_env

SECRET = "gsk_segredo_de_teste"
REQUEST = httpx.Request("POST", "https://api.example.com/v1/chat/completions")


def http_error(cls, status):
    response = httpx.Response(status, request=REQUEST)
    return cls(f"erro com a chave {SECRET}", response=response, body=None)


def reply(content, finish_reason="stop"):
    message = SimpleNamespace(content=content)
    return SimpleNamespace(choices=[SimpleNamespace(message=message, finish_reason=finish_reason)])


class FakeSDK:
    """Imita `OpenAI().chat.completions.create`; cada item é uma resposta ou exceção."""

    def __init__(self, *outcomes):
        self.outcomes = list(outcomes)
        self.requests = []
        self.chat = SimpleNamespace(completions=SimpleNamespace(create=self._create))

    def _create(self, **kwargs):
        self.requests.append(kwargs)
        outcome = self.outcomes.pop(0)
        if isinstance(outcome, Exception):
            raise outcome
        return outcome


def make_client(*outcomes, **overrides):
    sleeps = []
    sdk = FakeSDK(*outcomes)
    params = {"provider": "groq", "api_key": SECRET, "model": "modelo-x"}
    params.update(overrides)
    client = OpenAICompatibleClient(**params, sdk_client=sdk, sleep=sleeps.append)
    return client, sdk, sleeps


# --- client_from_env -------------------------------------------------------


@pytest.mark.parametrize("env", [{}, {"LLM_PROVIDER": ""}, {"LLM_PROVIDER": " MOCK "}])
def test_sem_provedor_usa_mock(env):
    assert isinstance(client_from_env(env), MockClient)


def test_groq_sem_chave_cita_a_variavel():
    with pytest.raises(LLMError, match="GROQ_API_KEY"):
        client_from_env({"LLM_PROVIDER": "groq", "GROQ_MODEL": "m"})


def test_openai_sem_modelo_cita_a_variavel():
    with pytest.raises(LLMError, match="OPENAI_MODEL"):
        client_from_env({"LLM_PROVIDER": "openai", "OPENAI_API_KEY": SECRET})


def test_provedor_desconhecido():
    with pytest.raises(LLMError, match="LLM_PROVIDER"):
        client_from_env({"LLM_PROVIDER": "gemini"})


def test_groq_le_configuracao_do_ambiente():
    client = client_from_env(
        {
            "LLM_PROVIDER": "groq",
            "GROQ_API_KEY": SECRET,
            "GROQ_MODEL": "openai/gpt-oss-120b",
            "LLM_TEMPERATURE": "0.5",
            "LLM_MAX_TOKENS": "900",
        }
    )
    assert (client.provider, client.model) == ("groq", "openai/gpt-oss-120b")
    assert (client.temperature, client.max_tokens) == (0.5, 900)
    assert str(client._sdk.base_url).startswith("https://api.groq.com/openai/v1")


def test_numero_invalido_no_ambiente():
    env = {"LLM_PROVIDER": "openai", "OPENAI_API_KEY": SECRET, "OPENAI_MODEL": "m"}
    with pytest.raises(LLMError, match="LLM_MAX_TOKENS"):
        client_from_env({**env, "LLM_MAX_TOKENS": "muitos"})


# --- MockClient ------------------------------------------------------------


def test_mock_ecoa_o_prompt_e_registra_chamadas():
    client = MockClient()
    assert client.complete("sistema", "paradas: A, B") == "[mock]\nparadas: A, B"
    assert client.calls == [("sistema", "paradas: A, B")]


# --- OpenAICompatibleClient ------------------------------------------------


def test_sucesso_envia_mensagens_e_parametros():
    client, sdk, sleeps = make_client(reply("  texto  "), temperature=0.1, max_tokens=50)

    assert client.complete("sys", "usr") == "texto"
    request = sdk.requests[0]
    assert request["model"] == "modelo-x"
    assert request["messages"] == [
        {"role": "system", "content": "sys"},
        {"role": "user", "content": "usr"},
    ]
    assert (request["temperature"], request["max_tokens"]) == (0.1, 50)
    assert sleeps == []


def test_429_seguido_de_sucesso_tenta_de_novo():
    client, sdk, sleeps = make_client(http_error(openai.RateLimitError, 429), reply("ok"))

    assert client.complete("s", "u") == "ok"
    assert len(sdk.requests) == 2
    assert sleeps == [2]


def test_erro_transitorio_esgota_tentativas_com_espera_exponencial():
    erros = [openai.APIConnectionError(request=REQUEST) for _ in range(4)]
    client, sdk, sleeps = make_client(*erros)

    with pytest.raises(LLMError, match="4 tentativas"):
        client.complete("s", "u")
    assert sleeps == [2, 4, 8]


def test_401_nao_tenta_de_novo_e_nao_expoe_a_chave():
    client, sdk, sleeps = make_client(http_error(openai.AuthenticationError, 401))

    with pytest.raises(LLMError, match="HTTP 401") as exc:
        client.complete("s", "u")
    assert SECRET not in str(exc.value)
    assert len(sdk.requests) == 1
    assert sleeps == []


@pytest.mark.parametrize("content", [None, "", "   "])
def test_resposta_vazia_e_erro(content):
    client, _, _ = make_client(reply(content))
    with pytest.raises(LLMError, match="resposta vazia"):
        client.complete("s", "u")


def test_resposta_cortada_pelo_limite_sugere_aumentar_tokens():
    client, _, _ = make_client(reply("", finish_reason="length"))
    with pytest.raises(LLMError, match="LLM_MAX_TOKENS"):
        client.complete("s", "u")


def test_chave_vazia_e_rejeitada():
    with pytest.raises(LLMError, match="chave"):
        OpenAICompatibleClient(provider="openai", api_key="", model="m")
