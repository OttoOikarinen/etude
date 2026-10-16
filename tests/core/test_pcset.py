# SPDX-FileCopyrightText: 2026 Otto Oikarinen
# SPDX-License-Identifier: GPL-3.0-or-later

from collections import Counter

import pytest
from hypothesis import given
from hypothesis import strategies as st

from etude.core import PitchClassSet
from etude.core.pcset import all_set_classes, format_prime_form

pc_sets = st.frozensets(st.integers(0, 11)).map(PitchClassSet)


def s(text: str) -> PitchClassSet:
    return PitchClassSet.parse(text)


def test_construction() -> None:
    assert PitchClassSet.of(0, 4, 7, 12) == s('047')
    assert s('[0, 4, 7, T]') == s('047A') == PitchClassSet.of(0, 4, 7, 10)
    assert s('{E, 2, 7}') == PitchClassSet.of(11, 2, 7)
    assert list(s('740')) == [0, 4, 7]
    assert len(s('0147')) == 4
    assert 4 in s('047')
    with pytest.raises(ValueError, match='0–11'):
        PitchClassSet(frozenset({12}))
    with pytest.raises(ValueError, match='not a pitch-class set'):
        s('0x')


def test_operations() -> None:
    triad = s('047')
    assert triad.transpose(2) == s('269')
    assert triad.invert() == s('058')
    assert triad.invert(7) == s('037')
    assert triad.complement() == s('1235689TE')
    assert triad.cardinality == 3


@pytest.mark.parametrize(
    ('pcs', 'normal', 'prime', 'vector', 'name'),
    [
        ('047', (0, 4, 7), (0, 3, 7), (0, 0, 1, 1, 1, 0), '3-11'),
        ('E27', (7, 11, 2), (0, 3, 7), (0, 0, 1, 1, 1, 0), '3-11'),
        ('0148', (0, 1, 4, 8), (0, 1, 4, 8), (1, 0, 1, 3, 1, 0), '4-19'),
        ('0369', (0, 3, 6, 9), (0, 3, 6, 9), (0, 0, 4, 0, 0, 2), '4-28'),
        ('7902', (7, 9, 0, 2), (0, 2, 5, 7), (0, 2, 1, 0, 3, 0), '4-23'),
        ('2579', (2, 5, 7, 9), (0, 2, 4, 7), (0, 2, 1, 1, 2, 0), '4-22'),
        ('0146', (0, 1, 4, 6), (0, 1, 4, 6), (1, 1, 1, 1, 1, 1), '4-Z15'),
        ('0137', (0, 1, 3, 7), (0, 1, 3, 7), (1, 1, 1, 1, 1, 1), '4-Z29'),
        ('B047', (11, 0, 4, 7), (0, 1, 5, 8), (1, 0, 1, 2, 2, 0), '4-20'),
        ('0347', (0, 3, 4, 7), (0, 3, 4, 7), (1, 0, 2, 2, 1, 0), '4-17'),
        ('024579E', (11, 0, 2, 4, 5, 7, 9), (0, 1, 3, 5, 6, 8, 10), (2, 5, 4, 3, 6, 1), '7-35'),
        ('0123456789TE', tuple(range(12)), tuple(range(12)), (12, 12, 12, 12, 12, 6), None),
        ('', (), (), (0, 0, 0, 0, 0, 0), None),
        ('04', (0, 4), (0, 4), (0, 0, 0, 1, 0, 0), None),
    ],
)
def test_forms(
    pcs: str,
    normal: tuple[int, ...],
    prime: tuple[int, ...],
    vector: tuple[int, ...],
    name: str | None,
) -> None:
    subject = s(pcs)
    assert subject.normal_form() == normal
    assert subject.prime_form() == prime
    assert subject.interval_vector() == vector
    assert subject.forte_name == name


def test_rahn_and_forte_differ_on_six_classes() -> None:
    differing = {
        c.forte_name: (
            format_prime_form(c.prime_form()),
            format_prime_form(c.prime_form(forte=True)),
        )
        for c in all_set_classes()
        if c.prime_form() != c.prime_form(forte=True)
    }
    assert differing == {
        '5-20': ('(01568)', '(01378)'),
        '6-Z29': ('(023679)', '(013689)'),
        '6-31': ('(014579)', '(013589)'),
        '7-Z18': ('(0145679)', '(0123589)'),
        '7-20': ('(0125679)', '(0124789)'),
        '8-26': ('(0134578T)', '(0124579T)'),
    }


def test_set_class_counts() -> None:
    classes = all_set_classes()
    assert len(classes) == 224
    counts = Counter(len(c) for c in classes)
    assert [counts[n] for n in range(13)] == [1, 1, 6, 12, 29, 38, 50, 38, 29, 12, 6, 1, 1]


def test_forte_names_cover_cardinalities_three_to_nine() -> None:
    named = [c for c in all_set_classes() if c.forte_name is not None]
    assert len(named) == 208
    assert len({c.forte_name for c in named}) == 208
    assert all(3 <= len(c) <= 9 for c in named)
    assert all(c.forte_name.startswith(f'{len(c)}-') for c in named)  # type: ignore[union-attr]


def test_complements_share_the_ordinal() -> None:
    for subject in all_set_classes():
        name = subject.forte_name
        if name is None:
            continue
        other = subject.complement().forte_name
        assert other is not None
        if len(subject) != 6:
            assert other.split('-')[1] == name.split('-')[1]
        elif 'Z' in name:
            assert other != name
            assert 'Z' in other
        else:
            assert other == name


def test_z_relations() -> None:
    z_count = 0
    for subject in all_set_classes():
        name = subject.forte_name
        if name is None:
            continue
        partner = subject.z_correspondent()
        assert ('Z' in name) == (partner is not None) == subject.is_z_related
        if partner is not None:
            z_count += 1
            assert partner.interval_vector() == subject.interval_vector()
            assert partner.z_correspondent() == subject.set_class()
    assert z_count == 46
    assert s('0146').z_correspondent() == s('0137')


@pytest.mark.parametrize(
    ('name', 'vector'),
    [
        ('4-10', '122010'),
        ('4-11', '121110'),
        ('5-21', '202420'),
        ('5-35', '032140'),
        ('6-1', '543210'),
        ('6-20', '303630'),
        ('6-Z13', '324222'),
        ('6-Z42', '324222'),
        ('6-30', '224223'),
        ('6-35', '060603'),
        ('8-28', '448444'),
        ('9-12', '666963'),
    ],
)
def test_known_vectors(name: str, vector: str) -> None:
    assert ''.join(map(str, PitchClassSet.from_forte_name(name).interval_vector())) == vector


def test_from_forte_name() -> None:
    assert PitchClassSet.from_forte_name('4-z15') == s('0146')
    assert PitchClassSet.from_forte_name('4-15') == s('0146')
    with pytest.raises(ValueError, match='not a Forte name'):
        PitchClassSet.from_forte_name('4-30')


def test_equivalence_and_display() -> None:
    assert s('047').is_tn_equivalent(s('48E'))
    assert not s('047').is_tn_equivalent(s('037'))
    assert s('047').is_tni_equivalent(s('037'))
    assert not s('047').is_tni_equivalent(s('0158'))
    assert str(s('E27')) == '[7,E,2]'
    assert format_prime_form((0, 1, 4, 10)) == '(014T)'


@given(pc_sets, st.integers(0, 11), st.integers(0, 11))
def test_round_trips(subject: PitchClassSet, n: int, m: int) -> None:
    assert subject.transpose(n).transpose(-n) == subject
    assert subject.invert(n).invert(n) == subject
    assert subject.complement().complement() == subject
    assert subject.transpose(n).transpose(m) == subject.transpose(n + m)


@given(pc_sets, st.integers(0, 11))
def test_invariance_under_tn_and_tni(subject: PitchClassSet, n: int) -> None:
    prime = subject.prime_form()
    assert subject.transpose(n).prime_form() == prime
    assert subject.invert(n).prime_form() == prime
    assert subject.invert(n).prime_form(forte=True) == subject.prime_form(forte=True)
    assert subject.transpose(n).interval_vector() == subject.interval_vector()
    # Normal forms of Tn-related sets have the same shape (symmetrical sets
    # may start on a different member).
    normal = subject.normal_form()
    shifted = subject.transpose(n).normal_form()
    assert [(pc - normal[0]) % 12 for pc in normal] == [(pc - shifted[0]) % 12 for pc in shifted]


@given(pc_sets)
def test_prime_form_properties(subject: PitchClassSet) -> None:
    prime = subject.prime_form()
    assert set(subject.normal_form()) == subject.pcs
    if subject.pcs:
        assert prime[0] == 0
        assert list(prime) == sorted(prime)
        assert PitchClassSet(frozenset(prime)).is_tni_equivalent(subject)
    vector = subject.interval_vector()
    assert sum(vector) == len(subject) * (len(subject) - 1) // 2
