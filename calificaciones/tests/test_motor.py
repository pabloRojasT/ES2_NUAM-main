"""Pruebas del motor de cálculo. No requieren base de datos ni Django."""
import unittest
from decimal import Decimal as D

from calificaciones import motor


class CalculoDeFactoresTests(unittest.TestCase):
    def test_ejemplo_a_tres_columnas_iguales(self):
        """Informe, sec. 4.1, ejemplo A: tres montos de 1.000.000."""
        montos = {8: D(1000000), 9: D(1000000), 10: D(1000000)}
        factores = motor.calcular_factores(montos)
        self.assertEqual(factores, {8: D("0.33333333"), 9: D("0.33333333"), 10: D("0.33333333")})
        resultado = motor.validar_suma(factores)
        self.assertEqual(resultado.suma, D("0.99999999"))
        self.assertTrue(resultado.cumple)

    def test_ejemplo_b_truncar_acepta(self):
        """Informe, ejemplo B: seis columnas de 500.000, truncando."""
        montos = {c: D(500000) for c in range(8, 14)}
        factores = motor.calcular_factores(montos, modo="truncar")
        self.assertTrue(all(f == D("0.16666666") for f in factores.values()))
        resultado = motor.validar_suma(factores)
        self.assertEqual(resultado.suma, D("0.99999996"))
        self.assertTrue(resultado.cumple)

    def test_ejemplo_b_redondear_bloquea(self):
        """Informe, ejemplo B: con redondeo la suma excede 1 y se bloquea."""
        montos = {c: D(500000) for c in range(8, 14)}
        factores = motor.calcular_factores(montos, modo="redondear")
        self.assertTrue(all(f == D("0.16666667") for f in factores.values()))
        resultado = motor.validar_suma(factores)
        self.assertEqual(resultado.suma, D("1.00000002"))
        self.assertFalse(resultado.cumple)

    def test_siempre_ocho_decimales_y_decimal(self):
        factores = motor.calcular_factores({8: D(1), 9: D(3)})
        self.assertEqual(factores[8], D("0.25000000"))
        self.assertEqual(factores[9], D("0.75000000"))
        for f in factores.values():
            self.assertIsInstance(f, D)
            self.assertEqual(f.as_tuple().exponent, -8)

    def test_monto_base_como_divisor(self):
        """Con un monto base explícito, la suma de factores puede exceder 1."""
        montos = {8: D(600000), 9: D(600000)}
        factores = motor.calcular_factores(montos, divisor=D(1000000))
        self.assertEqual(factores, {8: D("0.60000000"), 9: D("0.60000000")})
        resultado = motor.validar_suma(factores)
        self.assertEqual(resultado.suma, D("1.20000000"))
        self.assertFalse(resultado.cumple)

    def test_la_regla_solo_suma_las_columnas_del_rango(self):
        factores = {8: D("0.50000000"), 16: D("0.50000000"), 20: D("0.90000000")}
        resultado = motor.validar_suma(factores, columnas_regla=(8, 16))
        self.assertEqual(resultado.columnas, (8, 16))
        self.assertEqual(resultado.suma, D("1.00000000"))
        self.assertTrue(resultado.cumple)  # exactamente 1 cumple: la regla es "<= 1"

    def test_divisor_cero_es_error(self):
        with self.assertRaises(motor.ErrorCalculo):
            motor.calcular_factores({8: D(0), 9: D(0)})

    def test_sin_montos_es_error(self):
        with self.assertRaises(motor.ErrorCalculo):
            motor.calcular_factores({})

    def test_modo_desconocido_es_error(self):
        with self.assertRaises(motor.ErrorCalculo):
            motor.calcular_factores({8: D(1)}, modo="aproximar")


class ParseoDeMontosTests(unittest.TestCase):
    def test_enteros_y_decimales(self):
        self.assertEqual(motor.parsear_monto("500000"), D("500000"))
        self.assertEqual(motor.parsear_monto(" 1250,50 "), D("1250.50"))
        self.assertEqual(motor.parsear_monto("1250.5"), D("1250.5"))
        self.assertEqual(motor.parsear_monto(D("7")), D("7"))

    def test_rechaza_valores_invalidos(self):
        for malo in ["", "   ", "abc", "-5", "1.000.000", "1,5,5", "NaN", "Infinity", "1e3"]:
            with self.subTest(valor=malo):
                with self.assertRaises(motor.ErrorCalculo):
                    motor.parsear_monto(malo)

    def test_rechaza_demasiados_decimales(self):
        with self.assertRaises(motor.ErrorCalculo):
            motor.parsear_monto("1.1234567")

    def test_a_texto(self):
        self.assertEqual(motor.a_texto(D("0.5")), "0.50000000")
        self.assertEqual(motor.a_texto(D("1")), "1.00000000")


if __name__ == "__main__":
    unittest.main()
