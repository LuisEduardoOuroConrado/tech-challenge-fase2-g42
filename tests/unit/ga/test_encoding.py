import random

import pytest

from medroute.ga import create_individual, create_population, validate_chromosome


def test_individuo_e_permutacao_das_entregas(instance):
    chromosome = create_individual(instance, random.Random(1))
    assert sorted(chromosome) == sorted(d.id for d in instance.deliveries)


def test_populacao_tem_tamanho_pedido_e_e_valida(instance):
    population = create_population(instance, 10, random.Random(1))
    assert len(population) == 10
    for chromosome in population:
        validate_chromosome(chromosome, instance)


def test_populacao_reproduzivel_com_mesmo_seed(instance):
    assert create_population(instance, 5, random.Random(3)) == create_population(
        instance, 5, random.Random(3)
    )


def test_populacao_menor_que_dois_e_rejeitada(instance):
    with pytest.raises(ValueError):
        create_population(instance, 1, random.Random(0))


@pytest.mark.parametrize(
    "mutate",
    [
        lambda c: c[:-1],  # ausente
        lambda c: [*c, "x99"],  # extra
        lambda c: [c[0], *c[:-1]],  # duplicado
    ],
    ids=["ausente", "extra", "duplicado"],
)
def test_cromossomo_invalido_gera_value_error(instance, mutate):
    chromosome = [d.id for d in instance.deliveries]
    with pytest.raises(ValueError):
        validate_chromosome(mutate(chromosome), instance)
