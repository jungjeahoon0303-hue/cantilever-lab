# test_mechanics.py
# 버텨라 캔틸레버의 역학 계산을 손계산(교과서 공식)으로 검증하고,
# 각 재료가 어떤 하중에서 항복/파괴되는지 기준표를 출력한다.
# index.html 과 같은 상수를 사용한다 (값을 바꾸면 양쪽을 함께 바꿀 것).
import math

L = 6.0      # 보 길이 [m]
B = 0.18     # 폭 [m]
H = 0.28     # 높이(기본값) [m]
G = 9.81

MATERIALS = {            # E [MPa], fy [MPa], fu [MPa], 판정 방식
    'mild_steel': dict(E=200e3, fy=275, fu=410, kind='ductile'),
    'high_steel': dict(E=200e3, fy=500, fu=620, kind='ductile'),
    'concrete':   dict(E=25e3,  fy=3.2, fu=3.5, kind='brittle'),
    'wood':       dict(E=11e3,  fy=30,  fu=42,  kind='brittle'),
    'rubber':     dict(E=150,   fy=40,  fu=60,  kind='rubber'),
}
LOADS = {'worker': 75, 'weight100': 100, 'block500': 500, 'car': 1500, 'heavy': 5000}


def section(h=H):
    I = B * h ** 3 / 12
    S = B * h ** 2 / 6
    return I, S


def tip_deflection(P, a, E_mpa, h=H):
    """끝단 처짐: 하중점 a 까지는 Pa²(3L−a)/(6EI) 형태 (a=L 이면 PL³/3EI)."""
    I, _ = section(h)
    EI = E_mpa * 1e6 * I
    return P * a ** 2 * (3 * L - a) / (6 * EI)


def test_section_properties():
    I, S = section()
    assert math.isclose(I, 3.2928e-4, rel_tol=1e-4)
    assert math.isclose(S, 2.352e-3, rel_tol=1e-4)


def test_tip_load_formula_matches_classic():
    P = 1000.0
    E = 200e3
    I, _ = section()
    classic = P * L ** 3 / (3 * E * 1e6 * I)
    assert math.isclose(tip_deflection(P, L, E), classic, rel_tol=1e-12)


def test_superposition_moment():
    loads = [(75 * G, 5.0), (100 * G, 4.0)]
    M = sum(P * x for P, x in loads)
    assert math.isclose(M / 1000, 7.60275, rel_tol=1e-9)   # E2E 15번과 동일한 값


def test_numeric_case_used_in_e2e():
    P, a = 500 * G, 3.0
    _, S = section()
    assert math.isclose(P * a / 1000, 14.715, rel_tol=1e-9)
    assert math.isclose(P * a / S / 1e6, 6.2564, rel_tol=1e-4)
    assert math.isclose(tip_deflection(P, a, 200e3) * 100, 0.16758, rel_tol=1e-3)


def test_concrete_breaks_with_one_block_but_not_one_worker():
    _, S = section()
    m = MATERIALS['concrete']
    sigma_block = 500 * G * 5.69 / S / 1e6
    sigma_worker = 75 * G * 5.79 / S / 1e6
    assert sigma_block > m['fu'], sigma_block
    assert sigma_worker < m['fy'], sigma_worker


def test_thickness_effect():
    # h 를 1.5배 → I 는 3.375배(처짐 1/3.375), S 는 2.25배(응력 1/2.25)
    I1, S1 = section(0.20)
    I2, S2 = section(0.30)
    assert math.isclose(I2 / I1, 1.5 ** 3, rel_tol=1e-12)
    assert math.isclose(S2 / S1, 1.5 ** 2, rel_tol=1e-12)


# ── 소성 잔류 처짐: 앱과 같은 σ-ε 곡선(연강)으로 정밀 적분한 기준값
#    δp = ∫0^L κp(ξ)·(L−ξ) dξ,  κp = 2·εp/h,  εp = ε(σ) − σ/E,  σ = M(ξ)/S
def mild_steel_eps_p(s):
    E, fy, fu, eu = 200e3, 275.0, 410.0, 0.16
    ey = fy / E
    if s <= fy:
        return 0.0
    s = min(s, fu)
    r = (s - fy) / (fu - fy)
    return max(0.0, ey + (eu - ey) * r * r - s / E)


def residual_tip_exact(loads, h=H, n=200000):
    _, S = section(h)
    d = L / n
    tot = 0.0
    for i in range(n):
        xi = (i + 0.5) * d
        M = sum(P * (a - xi) for P, a in loads if a > xi)
        tot += 2 * mild_steel_eps_p(M / S / 1e6) / h * (L - xi) * d
    return tot


def test_plastic_residual_reference():
    loads = [(5000 * G, 5.9), (5000 * G, 5.0), (5000 * G, 4.2)]   # E2E 10번과 같은 조건
    d = residual_tip_exact(loads) * 100
    assert abs(d - 12.030) < 0.01, d          # 앱 값(12.038 cm)은 E2E 에서 이 기준과 0.5% 이내로 비교


def print_reference_table():
    _, S = section()
    print(f"단면: b={B} m, h={H} m → S={S:.4e} m³")
    print(f"{'재료':<11}{'끝단 항복하중':>14}{'끝단 파괴하중':>14}   (x = L 에 집중하중일 때, kg)")
    for k, m in MATERIALS.items():
        Wy = m['fy'] * 1e6 * S / L / G
        Wu = m['fu'] * 1e6 * S / L / G
        print(f"{k:<11}{Wy:>14,.0f}{Wu:>14,.0f}")
    print()
    print("하중물을 끝단(x≈5.7 m)에 하나 올렸을 때 고정단 응력 [MPa]:")
    for name, w in LOADS.items():
        print(f"  {name:<10}{w:>6} kg → σ = {w * G * 5.7 / S / 1e6:7.2f} MPa")


if __name__ == '__main__':
    tests = [v for k, v in dict(globals()).items() if k.startswith('test_')]
    for t in tests:
        t()
        print(f"PASS {t.__name__}")
    print()
    print_reference_table()
    print(f"\n{len(tests)} mechanics tests passed.")
