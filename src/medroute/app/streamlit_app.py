"""App Streamlit do medroute: instância → otimizar → mapa → instruções → relatório → pergunta.

Rodar da raiz do repositório (os caminhos são os mesmos da CLI):

    medroute app            # ou: streamlit run src/medroute/app/streamlit_app.py
"""

from pathlib import Path

import pandas as pd
import streamlit as st
import streamlit.components.v1 as components

from medroute.app.cli import FITNESS_PATH, FLEET_PATH, INSTANCES_DIR, RESULTS_DIR, _llm_client
from medroute.data import DistanceMatrix, load_fleet, load_instance
from medroute.data.cli import INSTANCIAS
from medroute.domain.models import Instance, Priority, Solution
from medroute.ga import GAConfig, GeneticAlgorithm, load_fitness_config, make_fitness
from medroute.llm import LLMError, answer, generate_instructions, generate_report
from medroute.viz import build_map

PROVEDORES = ["mock", "groq", "openai"]
PERGUNTAS_EXEMPLO = [
    "A que horas são atendidas as entregas críticas e qual o prazo de cada uma?",
    "Qual veículo volta por último ao depósito e a que horas?",
    "Quantas entregas críticas cada veículo faz?",
    "Qual rota custa mais caro?",
]


def load_data(nome: str) -> tuple[Instance, DistanceMatrix]:
    fleet = load_fleet(FLEET_PATH)
    instance = load_instance(INSTANCES_DIR / f"{nome}.json", fleet)
    return instance, DistanceMatrix(instance, fleet)


def optimize(nome: str, seed: int, config: GAConfig) -> Solution:
    """Roda o GA com o fitness definitivo, como o `medroute solve`."""
    instance, dm = load_data(nome)
    fitness_fn = make_fitness(
        instance, dm, load_fleet(FLEET_PATH), load_fitness_config(FITNESS_PATH)
    )
    return GeneticAlgorithm(instance, dm, config, fitness_fn).run(seed)


def saved_solutions(nome: str) -> list[Path]:
    """JSONs de uma Solution da instância salvos pelo `medroute solve`."""
    return sorted(RESULTS_DIR.glob(f"{nome}_*.json"))


def routes_table(solution: Solution, instance: Instance) -> pd.DataFrame:
    prioridade = {delivery.id: delivery.prioridade for delivery in instance.deliveries}
    linhas = []
    for route in solution.routes:
        violacoes = ", ".join(f"{k}={v:.2f}" for k, v in route.violacoes.items() if v) or "-"
        linhas.append(
            {
                "Veículo": route.vehicle_id,
                "Entregas": len(route.sequence),
                "Críticas": sum(prioridade[stop] is Priority.CRITICA for stop in route.sequence),
                "km": round(route.distancia_km, 1),
                "min": round(route.duracao_min),
                "Carga kg": round(route.carga_kg, 1),
                "Custo R$": round(route.custo, 2),
                "Violações": violacoes,
            }
        )
    return pd.DataFrame(linhas)


def _sidebar() -> dict:
    with st.sidebar:
        st.header("Instância")
        nome = st.selectbox("Instância", list(INSTANCIAS), index=1, key="inst")
        origem = st.radio(
            "Solução", ["Otimizar agora", "Usar solução salva"], key="origem", horizontal=True
        )
        params: dict = {"nome": nome, "origem": origem}
        if origem == "Otimizar agora":
            st.header("Algoritmo genético")
            params["seed"] = st.number_input("Seed", min_value=0, value=7, step=1, key="seed")
            params["populacao"] = st.slider("População", 10, 300, 100, 10, key="populacao")
            params["geracoes"] = st.slider("Gerações", 5, 600, 300, 5, key="geracoes")
            params["crossover"] = st.selectbox("Crossover", ["ox", "pmx"], key="crossover")
            params["hibrido"] = st.toggle(
                "GA híbrido (semente NN + 2-opt)", value=True, key="hibrido"
            )
        else:
            arquivos = saved_solutions(nome)
            params["arquivo"] = st.selectbox(
                "Arquivo",
                arquivos,
                format_func=lambda p: p.name,
                key="arquivo",
                help=f"JSONs salvos em {RESULTS_DIR} pelo `medroute solve`.",
            )
        st.header("LLM")
        params["provedor"] = st.selectbox(
            "Provedor",
            PROVEDORES,
            key="provedor",
            help="mock não usa rede; openai usa o crédito pré-pago (respostas ficam em cache).",
        )
    return params


def _resolve_solution(params: dict) -> None:
    """Gera ou carrega a Solution e guarda no estado da sessão."""
    if params["origem"] == "Otimizar agora":
        if not st.sidebar.button("Otimizar rotas", type="primary", key="otimizar"):
            return
        # Mesmos padrões do `medroute solve`.
        config = GAConfig(
            population_size=params["populacao"],
            generations=params["geracoes"],
            crossover_rate=0.9,
            mutation_rate=0.2,
            elitism=2,
            tournament_size=3,
            crossover=params["crossover"],
            mutation="inversion",
            seed_nearest_neighbor=params["hibrido"],
            local_search_rate=0.3 if params["hibrido"] else 0.0,
        )
        with st.spinner("Otimizando..."):
            solution = optimize(params["nome"], int(params["seed"]), config)
    else:
        arquivo = params.get("arquivo")
        if arquivo is None:
            st.sidebar.info("Nenhuma solução salva desta instância: rode `medroute solve`.")
            return
        if not st.sidebar.button("Carregar solução", type="primary", key="carregar"):
            return
        solution = Solution.model_validate_json(Path(arquivo).read_text(encoding="utf-8"))
    st.session_state["solution"] = solution
    for chave in ("instrucoes", "relatorio", "resposta"):
        st.session_state.pop(chave, None)


def _llm(provedor: str):
    try:
        return _llm_client(provedor)
    except LLMError as error:
        st.error(f"LLM indisponível: {error}")
        return None


def _resultado(solution: Solution) -> None:
    penalidades = sum(solution.penalidades.values())
    prioridade = solution.fitness - solution.custo_operacional - penalidades
    colunas = st.columns(5)
    colunas[0].metric("Fitness", f"R$ {solution.fitness:,.2f}")
    colunas[1].metric("Operacional", f"R$ {solution.custo_operacional:,.2f}")
    colunas[2].metric("Prioridade", f"R$ {prioridade:,.2f}")
    colunas[3].metric("Distância", f"{solution.distancia_total_km:.1f} km")
    colunas[4].metric("Veículos", len(solution.routes))
    if penalidades:
        st.warning(f"Penalidades: R$ {penalidades:,.2f} ({solution.penalidades})")
    st.caption(
        f"{solution.algoritmo} · seed {solution.seed} · {len(solution.historico_fitness)} "
        f"gerações · {solution.tempo_exec_s:.2f} s"
    )


def main() -> None:
    st.set_page_config(page_title="medroute", layout="wide")
    st.title("medroute · rotas para distribuição hospitalar")
    st.caption("Algoritmo genético para as rotas; LLM para instruções, relatórios e perguntas.")

    params = _sidebar()
    _resolve_solution(params)
    solution: Solution | None = st.session_state.get("solution")
    if solution is None:
        st.info(
            "Escolha a instância e clique em **Otimizar rotas** (ou carregue uma solução salva)."
        )
        return
    instance, _ = load_data(solution.instance_nome)
    _resultado(solution)

    aba_mapa, aba_rotas, aba_instr, aba_rel, aba_qa = st.tabs(
        ["Mapa", "Rotas", "Instruções", "Relatório", "Perguntas"]
    )
    with aba_mapa:
        components.html(build_map(solution, instance).get_root().render(), height=560)
    with aba_rotas:
        st.dataframe(routes_table(solution, instance), hide_index=True)
        if solution.historico_fitness:
            st.subheader("Convergência do GA")
            st.line_chart(
                pd.DataFrame({"Fitness (R$)": solution.historico_fitness}),
                x_label="Geração",
                y_label="R$",
            )
    with aba_instr:
        if st.button("Gerar instruções por motorista", key="btn_instrucoes"):
            client = _llm(params["provedor"])
            if client is not None:
                with st.spinner(f"Gerando instruções ({client.provider})..."):
                    try:
                        st.session_state["instrucoes"] = generate_instructions(
                            solution, instance, client, load_fleet(FLEET_PATH)
                        )
                    except LLMError as error:
                        st.error(f"Erro na LLM: {error}")
        for vehicle_id, texto in st.session_state.get("instrucoes", {}).items():
            with st.expander(vehicle_id, expanded=True):
                st.markdown(texto)
    with aba_rel:
        periodo = st.radio("Período", ["diario", "semanal"], horizontal=True, key="periodo")
        if st.button("Gerar relatório", key="btn_relatorio"):
            client = _llm(params["provedor"])
            if client is not None:
                with st.spinner(f"Gerando relatório ({client.provider})..."):
                    try:
                        st.session_state["relatorio"] = generate_report(
                            [solution], instance, periodo, client
                        )
                    except LLMError as error:
                        st.error(f"Erro na LLM: {error}")
        if "relatorio" in st.session_state:
            st.markdown(st.session_state["relatorio"])
    with aba_qa:
        exemplo = st.selectbox("Exemplos", PERGUNTAS_EXEMPLO, key="exemplo")
        livre = st.text_input(
            "Pergunta sobre as rotas", placeholder="Vazio = usa o exemplo", key="pergunta"
        )
        pergunta = livre.strip() or exemplo
        if st.button("Perguntar", key="btn_perguntar"):
            client = _llm(params["provedor"])
            if client is not None:
                with st.spinner(f"Consultando a LLM ({client.provider})..."):
                    try:
                        st.session_state["resposta"] = answer(
                            pergunta, solution, instance, client, load_fleet(FLEET_PATH)
                        )
                    except (LLMError, ValueError) as error:
                        st.error(f"Não foi possível responder: {error}")
        if "resposta" in st.session_state:
            st.markdown(st.session_state["resposta"])


main()
