from decimal import Decimal as D

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
from django.urls import reverse

from bitacora.models import Registro
from calificaciones import services
from calificaciones.models import Calificacion, Mercado, Origen
from calificaciones.tests.test_carga import csv_de_prueba
from cuentas.models import Perfil
from cuentas.testing import CLAVE_PRUEBA, crear_corredora, crear_usuario


class VistasBase(TestCase):
    def setUp(self):
        self.andina = crear_corredora("Corredora Andina S.A.")
        self.boreal = crear_corredora("Corredora Boreal Ltda.")
        self.analista = crear_usuario("ana", self.andina, Perfil.Rol.ANALISTA)
        self.admin = crear_usuario("adm", self.andina, Perfil.Rol.ADMIN)
        self.auditor = crear_usuario("aud", self.andina, Perfil.Rol.AUDITOR)
        self.ajeno = crear_usuario("luis", self.boreal, Perfil.Rol.ANALISTA)

    def entrar(self, usuario):
        self.assertTrue(self.client.login(username=usuario.username, password=CLAVE_PRUEBA))

    def crear(self, usuario, instrumento="ACCION-ALFA", **cambios):
        datos = dict(
            ejercicio=2025,
            mercado=Mercado.ACCIONES,
            instrumento=instrumento,
            secuencia=1,
            origen=Origen.CORREDOR,
            montos={8: D(1000000), 9: D(1000000), 10: D(1000000)},
        )
        datos.update(cambios)
        return services.guardar_calificacion(usuario, **datos).calificacion

    def post_formulario(self, accion="guardar", **cambios):
        datos = {
            "ejercicio": "2025",
            "mercado": "ACCIONES",
            "instrumento": "ACCION-NUEVA",
            "secuencia": "1",
            "origen": "CORREDOR",
            "monto_8": "1000000",
            "monto_9": "1000000",
            "monto_10": "1000000",
            "accion": accion,
        }
        datos.update(cambios)
        return self.client.post(reverse("calificaciones:nueva"), datos)


class AccesoYListaTests(VistasBase):
    def test_exige_iniciar_sesion(self):
        respuesta = self.client.get(reverse("calificaciones:lista"))
        self.assertEqual(respuesta.status_code, 302)
        self.assertIn("/ingresar/", respuesta["Location"])

    def test_la_lista_solo_muestra_datos_de_la_propia_corredora(self):
        self.crear(self.analista, "ACCION-ANDINA")
        self.crear(self.ajeno, "ACCION-BOREAL")
        self.entrar(self.auditor)
        respuesta = self.client.get(reverse("calificaciones:lista"))
        self.assertContains(respuesta, "ACCION-ANDINA")
        self.assertNotContains(respuesta, "ACCION-BOREAL")

    def test_los_filtros_de_la_lista(self):
        self.crear(self.analista, "ACCION-A")
        self.crear(self.analista, "CFI-B", mercado=Mercado.CFI)
        self.entrar(self.analista)
        respuesta = self.client.get(reverse("calificaciones:lista"), {"mercado": "CFI"})
        self.assertContains(respuesta, "CFI-B")
        self.assertNotContains(respuesta, "ACCION-A")
        respuesta = self.client.get(reverse("calificaciones:lista"), {"q": "accion"})
        self.assertContains(respuesta, "ACCION-A")
        self.assertNotContains(respuesta, "CFI-B")

    def test_las_eliminadas_no_aparecen(self):
        calificacion = self.crear(self.analista, "ACCION-BORRADA")
        services.eliminar_logico(self.analista, calificacion)
        self.entrar(self.analista)
        self.assertNotContains(self.client.get(reverse("calificaciones:lista")), "ACCION-BORRADA")

    def test_el_auditor_no_ve_botones_de_edicion(self):
        self.crear(self.analista)
        self.entrar(self.auditor)
        respuesta = self.client.get(reverse("calificaciones:lista"))
        self.assertNotContains(respuesta, "Nueva calificación")
        self.assertNotContains(respuesta, "Eliminar")


class FormularioTests(VistasBase):
    def test_guardar_crea_la_calificacion(self):
        self.entrar(self.analista)
        respuesta = self.post_formulario()
        self.assertRedirects(respuesta, reverse("calificaciones:lista"))
        c = Calificacion.objects.get(instrumento="ACCION-NUEVA")
        self.assertEqual(c.corredora, self.andina)
        self.assertEqual(c.suma_factores, D("0.99999999"))
        self.assertTrue(Registro.objects.filter(operacion=Registro.Operacion.INGRESO).exists())

    def test_calcular_muestra_los_factores_sin_guardar(self):
        self.entrar(self.analista)
        respuesta = self.post_formulario(accion="calcular")
        self.assertEqual(respuesta.status_code, 200)
        self.assertContains(respuesta, "0,33333333")
        self.assertEqual(Calificacion.objects.count(), 0)

    def test_rn1_bloquea_el_guardado_y_lo_explica(self):
        self.entrar(self.analista)
        respuesta = self.post_formulario(monto_8="600000", monto_9="600000", monto_10="", monto_base="1000000")
        self.assertEqual(respuesta.status_code, 200)
        self.assertContains(respuesta, "Guardado bloqueado")
        self.assertContains(respuesta, "1,20000000")
        self.assertEqual(Calificacion.objects.count(), 0)

    def test_calcular_tambien_avisa_si_la_suma_excede_uno(self):
        self.entrar(self.analista)
        respuesta = self.post_formulario(
            accion="calcular", monto_8="600000", monto_9="600000", monto_10="", monto_base="1000000"
        )
        self.assertContains(respuesta, "Guardado bloqueado")
        self.assertNotContains(respuesta, "Válida")

    def test_monto_invalido_se_informa(self):
        self.entrar(self.analista)
        respuesta = self.post_formulario(monto_8="abc")
        self.assertContains(respuesta, "Columna 8")
        self.assertEqual(Calificacion.objects.count(), 0)

    def test_editar_recalcula_y_registra_la_modificacion(self):
        calificacion = self.crear(self.analista)
        self.entrar(self.analista)
        respuesta = self.client.post(
            reverse("calificaciones:editar", args=[calificacion.pk]),
            {"monto_8": "2000000", "monto_9": "1000000", "monto_10": "1000000", "accion": "guardar"},
        )
        self.assertRedirects(respuesta, reverse("calificaciones:lista"))
        calificacion.refresh_from_db()
        self.assertEqual(calificacion.factores["8"], "0.50000000")
        self.assertTrue(Registro.objects.filter(operacion=Registro.Operacion.MODIFICACION).exists())

    def test_el_auditor_recibe_403_y_queda_el_intento_en_la_bitacora(self):
        self.entrar(self.auditor)
        respuesta = self.post_formulario()
        self.assertEqual(respuesta.status_code, 403)
        self.assertEqual(Calificacion.objects.count(), 0)
        intento = Registro.objects.get(operacion=Registro.Operacion.INTENTO_RECHAZADO)
        self.assertEqual(intento.usuario, self.auditor)

    def test_editar_una_calificacion_de_otra_corredora_da_403_y_queda_registrado(self):
        ajena = self.crear(self.ajeno, "ACCION-BOREAL")
        self.entrar(self.analista)
        respuesta = self.client.get(reverse("calificaciones:editar", args=[ajena.pk]))
        self.assertEqual(respuesta.status_code, 403)
        intento = Registro.objects.get(operacion=Registro.Operacion.INTENTO_RECHAZADO)
        self.assertEqual(intento.usuario, self.analista)
        self.assertIn("RN6", intento.detalle)

    def test_eliminar_pide_confirmacion_y_luego_elimina_en_forma_logica(self):
        calificacion = self.crear(self.analista)
        self.entrar(self.analista)
        url = reverse("calificaciones:eliminar", args=[calificacion.pk])
        self.assertContains(self.client.get(url), "¿Eliminar ACCION-ALFA")
        calificacion.refresh_from_db()
        self.assertFalse(calificacion.eliminada)  # el GET no elimina
        self.assertRedirects(self.client.post(url), reverse("calificaciones:lista"))
        calificacion.refresh_from_db()
        self.assertTrue(calificacion.eliminada)


class CargaMasivaVistasTests(VistasBase):
    def subir(self, texto, nombre="calificaciones_2025.csv"):
        archivo = SimpleUploadedFile(nombre, texto.encode("utf-8"), content_type="text/csv")
        return self.client.post(reverse("calificaciones:carga"), {"archivo": archivo})

    def test_flujo_completo_en_tres_pasos(self):
        self.entrar(self.analista)
        self.assertRedirects(self.subir(csv_de_prueba()), reverse("calificaciones:carga_previa"))

        previa = self.client.get(reverse("calificaciones:carga_previa"))
        self.assertEqual(previa.context["total"], 100)
        self.assertEqual(previa.context["validas"], 96)
        self.assertEqual(previa.context["con_error"], 4)
        self.assertEqual(Calificacion.objects.count(), 0)

        confirmar = self.client.post(reverse("calificaciones:carga_confirmar"))
        self.assertRedirects(confirmar, reverse("calificaciones:carga_resultado"))
        resultado = self.client.get(reverse("calificaciones:carga_resultado"))
        self.assertEqual(resultado.context["resultado"]["nuevas"], 96)
        self.assertContains(resultado, "Fila 17")
        self.assertContains(resultado, "Fila 91")
        self.assertEqual(Calificacion.objects.count(), 96)

    def test_repetir_la_carga_no_duplica(self):
        self.entrar(self.analista)
        for _ in range(2):
            self.subir(csv_de_prueba())
            self.client.post(reverse("calificaciones:carga_confirmar"))
        self.assertEqual(Calificacion.objects.count(), 96)
        resultado = self.client.get(reverse("calificaciones:carga_resultado"))
        self.assertEqual(resultado.context["resultado"]["sin_cambios"], 96)

    def test_archivos_invalidos_se_rechazan(self):
        self.entrar(self.analista)
        self.assertEqual(self.subir("a,b\n1,2\n", nombre="datos.txt").status_code, 200)
        self.assertEqual(self.subir("a,b\n1,2\n").status_code, 200)  # faltan columnas
        self.assertEqual(Calificacion.objects.count(), 0)

    def test_confirmar_sin_archivo_vuelve_al_inicio(self):
        self.entrar(self.analista)
        self.assertRedirects(
            self.client.post(reverse("calificaciones:carga_confirmar")), reverse("calificaciones:carga")
        )

    def test_el_auditor_no_puede_cargar(self):
        self.entrar(self.auditor)
        self.assertEqual(self.client.get(reverse("calificaciones:carga")).status_code, 403)

    def test_la_plantilla_se_descarga_como_csv(self):
        self.entrar(self.analista)
        respuesta = self.client.get(reverse("calificaciones:carga_plantilla"))
        self.assertEqual(respuesta.status_code, 200)
        self.assertIn("text/csv", respuesta["Content-Type"])
        self.assertTrue(respuesta.content.decode().startswith("ejercicio,mercado,instrumento"))


class BitacoraVistaTests(VistasBase):
    def test_admin_y_auditor_consultan_solo_su_corredora(self):
        self.crear(self.analista, "ACCION-ANDINA")
        self.crear(self.ajeno, "ACCION-BOREAL")
        for usuario in (self.admin, self.auditor):
            self.entrar(usuario)
            respuesta = self.client.get(reverse("bitacora:lista"))
            self.assertContains(respuesta, "ACCION-ANDINA")
            self.assertNotContains(respuesta, "ACCION-BOREAL")
            self.client.logout()

    def test_el_analista_no_ve_la_bitacora(self):
        self.entrar(self.analista)
        self.assertEqual(self.client.get(reverse("bitacora:lista")).status_code, 403)

    def test_filtra_por_operacion(self):
        c = self.crear(self.analista, "ACCION-ANDINA")
        services.eliminar_logico(self.analista, c)
        self.entrar(self.auditor)
        respuesta = self.client.get(reverse("bitacora:lista"), {"operacion": "ELIMINACION"})
        self.assertEqual(respuesta.context["pagina"].paginator.count, 1)

    def test_no_acepta_escrituras(self):
        self.entrar(self.auditor)
        self.assertEqual(self.client.post(reverse("bitacora:lista"), {}).status_code, 405)
