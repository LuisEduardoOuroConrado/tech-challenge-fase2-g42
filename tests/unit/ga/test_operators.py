import random

import pytest

from medroute.ga import (
    inversion_mutation,
    order_crossover,
    pmx_crossover,
    swap_mutation,
    tournament_select,
    two_opt_local,
)

GENES = [f"g{i}" for i in range(10)]


@pytest.mark.parametrize("crossover", [order_crossover, pmx_crossover], ids=["ox", "pmx"])
def test_crossover_preserva_permutacao_e_nao_altera_pais(crossover):
    rng = random.Random(0)
    for _ in range(200):
        parent_a = rng.sample(GENES, len(GENES))
        parent_b = rng.sample(GENES, len(GENES))
        copy_a, copy_b = list(parent_a), list(parent_b)
        for child in crossover(parent_a, parent_b, rng):
            assert sorted(child) == sorted(GENES)
        assert (parent_a, parent_b) == (copy_a, copy_b)


def test_ox_mantem_segmento_do_pai_nas_mesmas_posicoes():
    class FixedCuts(random.Random):
        def sample(self, population, k):
            return [2, 5]

    parent_a = list("ABCDEFGH")
    parent_b = list("HGFEDCBA")
    child_a, child_b = order_crossover(parent_a, parent_b, FixedCuts())
    assert child_a[2:6] == list("CDEF")
    assert child_a == list("HGCDEFBA")
    assert child_b[2:6] == list("FEDC")


def test_pmx_resolve_conflitos_pelo_mapeamento():
    class FixedCuts(random.Random):
        def sample(self, population, k):
            return [3, 5]

    parent_a = [1, 2, 3, 4, 5, 6, 7, 8, 9]
    parent_b = [9, 3, 7, 8, 2, 6, 5, 1, 4]
    child_a, _ = pmx_crossover(parent_a, parent_b, FixedCuts())
    assert child_a == [9, 3, 7, 4, 5, 6, 2, 1, 8]


@pytest.mark.parametrize("mutation", [swap_mutation, inversion_mutation], ids=["swap", "inv"])
def test_mutacao_preserva_permutacao_e_nao_altera_original(mutation):
    rng = random.Random(0)
    original = list(GENES)
    for _ in range(100):
        mutant = mutation(original, rng)
        assert sorted(mutant) == sorted(GENES)
        assert mutant != original
    assert original == GENES


@pytest.mark.parametrize(
    "operator",
    [
        lambda c, rng: order_crossover(c, c, rng)[0],
        lambda c, rng: pmx_crossover(c, c, rng)[0],
        swap_mutation,
        inversion_mutation,
        lambda c, rng: two_opt_local(c, len),
    ],
    ids=["ox", "pmx", "swap", "inv", "2opt"],
)
@pytest.mark.parametrize("chromosome", [[], ["g0"]], ids=["vazio", "um-gene"])
def test_operadores_com_menos_de_dois_genes_devolvem_copia(operator, chromosome):
    result = operator(chromosome, random.Random(0))
    assert result == chromosome
    assert result is not chromosome


def test_inversion_inverte_segmento_inclusivo():
    class FixedCuts(random.Random):
        def sample(self, population, k):
            return [4, 1]

    assert inversion_mutation(list("ABCDEF"), FixedCuts()) == list("AEDCBF")


def test_torneio_escolhe_menor_fitness_e_devolve_copia():
    population = [["a"], ["b"], ["c"]]
    winner = tournament_select(population, [3.0, 1.0, 2.0], 3, random.Random(0))
    assert winner == ["b"]
    assert winner is not population[1]


@pytest.mark.parametrize("size", [1, 4])
def test_torneio_valida_tamanho(size):
    with pytest.raises(ValueError):
        tournament_select([["a"], ["b"], ["c"]], [1.0, 2.0, 3.0], size, random.Random(0))


def test_two_opt_nunca_piora_e_desfaz_cruzamento():
    def score(chromosome):
        positions = [int(gene[1:]) for gene in chromosome]
        return sum(abs(a - b) for a, b in zip(positions, positions[1:], strict=False))

    rng = random.Random(0)
    for _ in range(30):
        start = rng.sample(GENES, len(GENES))
        improved = two_opt_local(start, score, max_passes=5)
        assert sorted(improved) == sorted(GENES)
        assert score(improved) <= score(start)

    crossed = ["g0", "g3", "g2", "g1", "g4"]
    assert two_opt_local(crossed, score) == ["g0", "g1", "g2", "g3", "g4"]
