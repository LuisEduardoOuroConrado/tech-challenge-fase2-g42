import pytest
from conftest import make_instance, make_vehicle

from medroute.data import DistanceMatrix, FleetConfig
from medroute.domain.models import Priority, Route
from medroute.ga import GAConfig, GeneticAlgorithm, load_fitness_config, make_fitness
from medroute.ga.decoder import decode, split_decode
from medroute.ga.fitness import cronograma_rota

CFG = load_fitness_config()


def with_priorities(inst, priorities: dict[str, Priority]):
    deliveries = [
        d.model_copy(update={"prioridade": priorities.get(d.id, d.prioridade)})
        for d in inst.deliveries
    ]
    return inst.model_copy(update={"deliveries": deliveries})


def setup(inst):
    fleet = FleetConfig(vehicles=tuple(inst.fleet))
    dm = DistanceMatrix(inst)
    return dm, fleet, make_fitness(inst, dm, fleet, CFG)


def ids(inst) -> list[str]:
    return [d.id for d in inst.deliveries]


def test_config_do_repositorio_tem_os_pesos_da_spec():
    assert CFG.prioridade_rs_min == {
        Priority.CRITICA: 0.50,
        Priority.ALTA: 0.15,
        Priority.NORMAL: 0.05,
    }
    assert CFG.penalidades["capacidade"].fixo == 1000


def test_chave_ausente_no_yaml_gera_erro_claro(tmp_path):
    path = tmp_path / "fitness.yaml"
    path.write_text(
        "prioridade_rs_min: {critica: 0.5, alta: 0.15, normal: 0.05}\n"
        "penalidades:\n  capacidade: {fixo: 1000, unitario: 2000}\n",
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="autonomia"):
        load_fitness_config(path)


def test_sem_violacao_fitness_e_operacional_mais_prioridade():
    inst = make_instance(5)
    dm, _, fitness = setup(inst)
    routes = split_decode(ids(inst), inst, dm, CFG, fitness.servico_min)
    assert sum(fitness.penalties(routes).values()) == 0
    expected = sum(r.custo for r in routes) + fitness.priority_cost(routes)
    assert fitness(routes) == pytest.approx(expected)
    assert fitness.priority_cost(routes) > 0


@pytest.mark.parametrize(
    ("key", "amount"), [("capacidade", 0.001), ("autonomia", 0.1), ("capacidade", 0.5)]
)
def test_qualquer_violacao_hard_custa_pelo_menos_mil(key, amount):
    route = Route(
        vehicle_id="van-01",
        sequence=["e01"],
        distancia_km=1,
        duracao_min=1,
        carga_kg=1,
        carga_l=1,
        custo=10,
        violacoes={key: amount},
    )
    _, _, fitness = setup(make_instance(1))
    assert fitness.penalties([route])[key] >= 1000


def test_atender_a_critica_antes_reduz_o_fitness():
    inst = with_priorities(make_instance(4), {"e04": Priority.CRITICA})
    dm, _, fitness = setup(inst)
    critica_por_ultimo = ["e01", "e02", "e03", "e04"]
    critica_primeiro = ["e04", "e01", "e02", "e03"]
    # Mesma geometria percorrida nos dois sentidos não vale: compara só a prioridade.
    custo = {
        nome: fitness.priority_cost(decode(ordem, inst, dm))
        for nome, ordem in (("ultimo", critica_por_ultimo), ("primeiro", critica_primeiro))
    }
    assert custo["primeiro"] < custo["ultimo"]


def test_veiculo_sem_entregas_nao_aparece_nem_paga_fixo():
    fleet = [make_vehicle("van-01"), make_vehicle("van-02", custo_fixo=500.0)]
    inst = make_instance(3, fleet=fleet)
    dm, _, fitness = setup(inst)
    routes = split_decode(ids(inst), inst, dm, CFG, fitness.servico_min)
    assert [r.vehicle_id for r in routes] == ["van-01"]


def test_mesma_entrada_mesmo_fitness():
    inst = make_instance(6)
    dm, _, fitness = setup(inst)
    a = fitness(split_decode(ids(inst), inst, dm, CFG, fitness.servico_min))
    b = fitness(split_decode(ids(inst), inst, dm, CFG, fitness.servico_min))
    assert a == b


def test_pesos_alterados_no_yaml_mudam_o_fitness(tmp_path):
    texto = (
        open("configs/fitness.yaml", encoding="utf-8").read().replace("normal: 0.05", "normal: 1.0")
    )
    path = tmp_path / "fitness.yaml"
    path.write_text(texto, encoding="utf-8")
    inst = make_instance(4)
    dm, fleet, padrao = setup(inst)
    alterado = make_fitness(inst, dm, fleet, load_fitness_config(path))
    routes = decode(ids(inst), inst, dm)
    assert alterado(routes) > padrao(routes)


def test_cronograma_soma_viagem_e_servico_das_paradas_anteriores():
    inst = make_instance(3)
    dm, fleet, _ = setup(inst)
    vehicle = inst.fleet[0]
    chegadas = cronograma_rota(dm, vehicle, ["e01", "e02", "e03"], inst, fleet)
    v = vehicle.velocidade_kmh
    assert chegadas["e01"] == pytest.approx(dm.time(0, 1, v))
    assert chegadas["e03"] == pytest.approx(
        dm.time(0, 1, v) + dm.time(1, 2, v) + dm.time(2, 3, v) + 20
    )


# --- Split ótimo --------------------------------------------------------------------------


def test_split_preserva_a_ordem_e_todas_as_entregas():
    fleet = [make_vehicle("moto-01", tipo="moto", capacidade_kg=25.0, custo_fixo=10.0)] * 1
    fleet = [*fleet, make_vehicle("van-01")]
    inst = make_instance(6, fleet=fleet)
    dm, _, fitness = setup(inst)
    chromosome = ["e03", "e01", "e06", "e02", "e05", "e04"]
    routes = split_decode(chromosome, inst, dm, CFG, fitness.servico_min)
    assert [d for r in routes for d in r.sequence] == chromosome


def test_split_nunca_e_pior_que_o_guloso():
    fleet = [
        make_vehicle("moto-01", tipo="moto", capacidade_kg=30.0, custo_fixo=20.0, custo_km=0.8),
        make_vehicle("moto-02", tipo="moto", capacidade_kg=30.0, custo_fixo=20.0, custo_km=0.8),
        make_vehicle("van-01"),
    ]
    inst = with_priorities(make_instance(8, fleet=fleet), {"e08": Priority.CRITICA})
    dm, _, fitness = setup(inst)
    chromosome = ids(inst)
    split = fitness(split_decode(chromosome, inst, dm, CFG, fitness.servico_min))
    assert split <= fitness(decode(chromosome, inst, dm)) + 1e-9


def test_split_usa_mais_veiculos_quando_a_prioridade_compensa():
    gratis = {"custo_fixo": 0.0, "custo_km": 0.0}  # dividir só antecipa as chegadas
    fleet = [make_vehicle("van-01", **gratis), make_vehicle("van-02", **gratis)]
    criticas = {f"e{i:02d}": Priority.CRITICA for i in range(1, 9)}
    inst = with_priorities(make_instance(8, fleet=fleet), criticas)
    dm, _, fitness = setup(inst)
    routes = split_decode(ids(inst), inst, dm, CFG, fitness.servico_min)
    assert len(routes) == 2


def test_split_respeita_a_quantidade_de_veiculos():
    moto = {"tipo": "moto", "capacidade_kg": 25.0, "custo_fixo": 0.0, "custo_km": 0.0}
    fleet = [make_vehicle("moto-01", **moto), make_vehicle("moto-02", **moto)]
    inst = make_instance(4, fleet=fleet)  # 10 kg cada: precisa de 2 motos exatamente
    dm, _, fitness = setup(inst)
    routes = split_decode(ids(inst), inst, dm, CFG, fitness.servico_min)
    assert sorted(r.vehicle_id for r in routes) == ["moto-01", "moto-02"]
    assert all(not any(r.violacoes.values()) for r in routes)


def test_frota_insuficiente_cai_no_guloso_e_registra_violacao():
    inst = make_instance(3, fleet=[make_vehicle(capacidade_kg=15.0)])
    dm, _, fitness = setup(inst)
    routes = split_decode(ids(inst), inst, dm, CFG, fitness.servico_min)
    assert [d for r in routes for d in r.sequence] == ids(inst)
    assert routes[0].violacoes["capacidade"] > 0
    assert fitness.penalties(routes)["capacidade"] >= 1000


def test_custo_do_split_bate_com_o_fitness_das_rotas():
    fleet = [
        make_vehicle("moto-01", tipo="moto", capacidade_kg=30.0, custo_fixo=20.0, custo_km=0.8),
        make_vehicle("van-01"),
    ]
    inst = with_priorities(make_instance(7, fleet=fleet), {"e02": Priority.CRITICA})
    dm, _, fitness = setup(inst)
    routes = split_decode(ids(inst), inst, dm, CFG, fitness.servico_min)
    # o fitness recalculado pelas rotas (cronograma + pesos) tem de ser o mínimo que o DP achou:
    # nenhuma outra divisão viável da mesma ordem sai mais barata.
    assert fitness(routes) <= fitness(decode(ids(inst), inst, dm)) + 1e-9
    assert sum(fitness.penalties(routes).values()) == 0


def test_ga_com_fitness_definitivo_preenche_solution():
    fleet = [
        make_vehicle("moto-01", tipo="moto", capacidade_kg=30.0, custo_fixo=20.0, custo_km=0.8),
        make_vehicle("van-01"),
    ]
    inst = make_instance(6, fleet=fleet)
    dm, _, fitness = setup(inst)
    config = GAConfig(
        population_size=10,
        generations=5,
        crossover_rate=0.9,
        mutation_rate=0.2,
        elitism=1,
        tournament_size=2,
        crossover="ox",
        mutation="inversion",
    )
    solution = GeneticAlgorithm(inst, dm, config, fitness).run(seed=3)
    prioridade = solution.fitness - solution.custo_operacional - sum(solution.penalidades.values())
    assert prioridade == pytest.approx(fitness.priority_cost(solution.routes))
    assert solution.historico_fitness == sorted(solution.historico_fitness, reverse=True)
