from decimal import Decimal as D

from django.core.exceptions import PermissionDenied
from django.test import TestCase, override_settings

from bitacora.models import Registro
from calificaciones import services
from calificaciones.models import Calificacion, Mercado, Origen
from cuentas.models import Perfil
from cuentas.testing import crear_corredora, crear_usuario


class ServiciosTests(TestCase):
    def setUp(self):
        self.corredora = crear_corredora()
        self.analista = crear_usuario("ana", self.corredora, Perfil.Rol.ANALISTA)

    def guardar(self, usuario=None, **cambios):
        datos = dict(
            ejercicio=2025,
            mercado=Mercado.ACCIONES,
            instrumento="ACCION-ALFA",
            secuencia=1,
            origen=Origen.CORREDOR,
            montos={8: D(1000000), 9: D(1000000), 10: D(1000000)},
        )
        datos.update(cambios)
        return services.guardar_calificacion(usuario or self.analista, **datos)

    def test_crea_con_factores_y_suma(self):
        resultado = self.guardar()
        self.assertEqual(resultado.estado, "creada")
        c = resultado.calificacion
        self.assertEqual(c.factores, {"8": "0.33333333", "9": "0.33333333", "10": "0.33333333"})
        self.assertEqual(c.suma_factores, D("0.99999999"))
        self.assertEqual(c.corredora, self.corredora)

    def test_el_ingreso_queda_en_la_bitacora(self):
        self.guardar()
        registro = Registro.objects.get(operacion=Registro.Operacion.INGRESO)
        self.assertEqual(registro.usuario, self.analista)
        self.assertEqual(registro.corredora, self.corredora)
        self.assertEqual(registro.registro, "ACCION-ALFA · sec. 1")
        self.assertIn("0.99999999", registro.detalle)

    def test_guardar_lo_mismo_dos_veces_no_duplica_ni_registra_de_nuevo(self):
        self.guardar()
        segundo = self.guardar()
        self.assertEqual(segundo.estado, "sin_cambios")
        self.assertEqual(Calificacion.objects.count(), 1)
        self.assertEqual(Registro.objects.count(), 1)

    def test_modificar_actualiza_y_registra_los_cambios(self):
        self.guardar()
        resultado = self.guardar(montos={8: D(1000000), 9: D(2000000), 10: D(1000000)})
        self.assertEqual(resultado.estado, "actualizada")
        self.assertEqual(Calificacion.objects.count(), 1)
        registro = Registro.objects.get(operacion=Registro.Operacion.MODIFICACION)
        self.assertIn("Columna 9: monto de 1000000 a 2000000", registro.detalle)
        self.assertIn("La suma de factores pasó de", registro.detalle)

    def test_rn1_bloquea_y_no_deja_rastro(self):
        with self.assertRaises(services.ErrorValidacion) as contexto:
            self.guardar(montos={8: D(600000), 9: D(600000)}, monto_base=D(1000000))
        self.assertIn("RN1", contexto.exception.mensajes[0])
        self.assertIn("1.20000000", contexto.exception.mensajes[0])
        self.assertEqual(Calificacion.objects.count(), 0)
        self.assertEqual(Registro.objects.count(), 0)

    @override_settings(FACTORES_MODO_REDONDEO="redondear")
    def test_con_redondeo_seis_columnas_iguales_se_bloquean(self):
        montos = {c: D(500000) for c in range(8, 14)}
        with self.assertRaises(services.ErrorValidacion):
            self.guardar(montos=montos)

    def test_con_truncamiento_seis_columnas_iguales_se_guardan(self):
        montos = {c: D(500000) for c in range(8, 14)}
        self.assertEqual(self.guardar(montos=montos).calificacion.suma_factores, D("0.99999996"))

    def test_rn2_el_dato_de_bolsa_no_pisa_al_del_corredor(self):
        self.guardar(origen=Origen.CORREDOR)
        with self.assertRaises(services.ErrorValidacion) as contexto:
            self.guardar(origen=Origen.BOLSA, montos={8: D(1), 9: D(1)})
        self.assertIn("RN2", contexto.exception.mensajes[0])
        self.assertEqual(Calificacion.objects.get().origen, Origen.CORREDOR)

    def test_rn2_el_dato_del_corredor_si_reemplaza_al_de_bolsa(self):
        self.guardar(origen=Origen.BOLSA)
        self.guardar(origen=Origen.CORREDOR, montos={8: D(1), 9: D(1)})
        self.assertEqual(Calificacion.objects.get().origen, Origen.CORREDOR)

    def test_validaciones_de_identificacion(self):
        casos = [
            dict(instrumento="  "),
            dict(mercado="BONOS"),
            dict(ejercicio="abc"),
            dict(secuencia=0),
            dict(origen="OTRO"),
        ]
        for caso in casos:
            with self.subTest(caso=caso):
                with self.assertRaises(services.ErrorValidacion):
                    self.guardar(**caso)
        self.assertEqual(Calificacion.objects.count(), 0)

    def test_columnas_fuera_de_rango(self):
        with self.assertRaises(services.ErrorValidacion):
            self.guardar(montos={7: D(1), 8: D(1)})

    def test_eliminacion_logica_conserva_el_registro_y_lo_anota(self):
        calificacion = self.guardar().calificacion
        services.eliminar_logico(self.analista, calificacion)
        calificacion.refresh_from_db()
        self.assertTrue(calificacion.eliminada)
        self.assertEqual(Calificacion.objects.count(), 1)  # no se borró
        self.assertTrue(Registro.objects.filter(operacion=Registro.Operacion.ELIMINACION).exists())

    def test_volver_a_guardar_una_eliminada_la_reactiva(self):
        calificacion = self.guardar().calificacion
        services.eliminar_logico(self.analista, calificacion)
        resultado = self.guardar()
        self.assertEqual(resultado.estado, "actualizada")
        self.assertFalse(Calificacion.objects.get().eliminada)
        registro = Registro.objects.filter(operacion=Registro.Operacion.MODIFICACION).get()
        self.assertIn("se reactivó", registro.detalle)

    def test_la_llave_no_se_mezcla_entre_corredoras(self):
        otra = crear_corredora("Corredora Boreal Ltda.")
        otro = crear_usuario("luis", otra)
        self.guardar()
        self.guardar(usuario=otro)  # misma llave, otra corredora: es otro registro
        self.assertEqual(Calificacion.objects.count(), 2)

    def test_no_se_puede_eliminar_una_calificacion_de_otra_corredora(self):
        calificacion = self.guardar().calificacion
        otro = crear_usuario("luis", crear_corredora("Corredora Boreal Ltda."))
        with self.assertRaises(PermissionDenied):
            services.eliminar_logico(otro, calificacion)

    def test_obtener_de_otra_corredora_niega_y_registra_el_intento(self):
        calificacion = self.guardar().calificacion
        otro = crear_usuario("luis", crear_corredora("Corredora Boreal Ltda."))
        with self.assertRaises(PermissionDenied):
            services.obtener_calificacion(otro, calificacion.pk)
        intento = Registro.objects.get(operacion=Registro.Operacion.INTENTO_RECHAZADO)
        self.assertEqual(intento.usuario, otro)
