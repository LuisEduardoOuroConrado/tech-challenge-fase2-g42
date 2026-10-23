import numpy as np

from medroute.experiments.study_plots import _aligned_histories


def test_curvas_com_parada_antecipada_mantem_ultima_observacao():
    histories = [[100, 80], [120, 90, 60, 50], [110, 70, 65]]
    aligned = _aligned_histories(histories)
    np.testing.assert_array_equal(
        aligned, [[100, 80, 80, 80], [120, 90, 60, 50], [110, 70, 65, 65]]
    )
    np.testing.assert_allclose(aligned.mean(axis=0), [110, 80, 205 / 3, 65])
    np.testing.assert_allclose(aligned.std(axis=0, ddof=1)[-1], 15)
    assert [len(h) for h in histories] == [2, 4, 3]
