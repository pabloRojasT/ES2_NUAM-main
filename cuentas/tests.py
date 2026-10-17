from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from bitacora.models import Registro

from .models import Perfil
from .permisos import tiene_permiso
from .testing import CLAVE_PRUEBA, crear_corredora, crear_usuario

User = get_user_model()


class PermisosTests(TestCase):
    def setUp(self):
        self.corredora = crear_corredora()

    def test_matriz_de_permisos_por_rol(self):
        esperado = {
            Perfil.Rol.ANALISTA: {"consultar": True, "editar": True, "ver_bitacora": False, "gestionar_usuarios": False},
            Perfil.Rol.ADMIN: {"consultar": True, "editar": True, "ver_bitacora": True, "gestionar_usuarios": True},
            Perfil.Rol.AUDITOR: {"consultar": True, "editar": False, "ver_bitacora": True, "gestionar_usuarios": False},
        }
        for rol, permisos in esperado.items():
            usuario = crear_usuario(f"u-{rol}", self.corredora, rol)
            for permiso, debe in permisos.items():
                with self.subTest(rol=rol, permiso=permiso):
                    self.assertEqual(tiene_permiso(usuario, permiso), debe)

    def test_un_usuario_sin_perfil_no_tiene_ningun_permiso(self):
        sin_perfil = User.objects.create_user("sinperfil", password=CLAVE_PRUEBA)
        self.assertFalse(tiene_permiso(sin_perfil, "consultar"))

    def test_un_usuario_desactivado_no_tiene_permisos(self):
        usuario = crear_usuario("ana", self.corredora)
        usuario.is_active = False
        self.assertFalse(tiene_permiso(usuario, "consultar"))


class InicioDeSesionTests(TestCase):
    def setUp(self):
        self.corredora = crear_corredora()
        self.usuario = crear_usuario("ana", self.corredora)

    def test_login_correcto_redirige_y_queda_en_la_bitacora(self):
        respuesta = self.client.post(
            reverse("cuentas:ingresar"), {"username": "ana", "password": CLAVE_PRUEBA}
        )
        self.assertRedirects(respuesta, "/calificaciones/", fetch_redirect_response=False)
        acceso = Registro.objects.get(operacion=Registro.Operacion.ACCESO)
        self.assertEqual(acceso.usuario, self.usuario)

    def test_login_incorrecto_no_entra(self):
        respuesta = self.client.post(reverse("cuentas:ingresar"), {"username": "ana", "password": "mala"})
        self.assertEqual(respuesta.status_code, 200)
        self.assertContains(respuesta, "incorrectos")
        self.assertEqual(Registro.objects.count(), 0)

    def test_salir_cierra_la_sesion(self):
        self.client.login(username="ana", password=CLAVE_PRUEBA)
        self.client.post(reverse("cuentas:salir"))
        self.assertEqual(self.client.get(reverse("calificaciones:lista")).status_code, 302)


class GestionDeUsuariosTests(TestCase):
    def setUp(self):
        self.andina = crear_corredora("Corredora Andina S.A.")
        self.boreal = crear_corredora("Corredora Boreal Ltda.")
        self.admin = crear_usuario("adm", self.andina, Perfil.Rol.ADMIN)
        self.analista = crear_usuario("ana", self.andina, Perfil.Rol.ANALISTA)
        self.ajeno = crear_usuario("luis", self.boreal, Perfil.Rol.ANALISTA)

    def entrar(self, usuario):
        self.client.login(username=usuario.username, password=CLAVE_PRUEBA)

    def test_solo_el_administrador_entra(self):
        self.entrar(self.analista)
        self.assertEqual(self.client.get(reverse("cuentas:usuarios")).status_code, 403)
        self.assertTrue(Registro.objects.filter(operacion=Registro.Operacion.INTENTO_RECHAZADO).exists())

    def test_el_administrador_crea_un_usuario_en_su_corredora(self):
        self.entrar(self.admin)
        respuesta = self.client.post(
            reverse("cuentas:usuarios"),
            {"correo": "Nuevo@Ejemplo.cl", "nombre": "Nueva Persona", "rol": "AUDITOR", "clave": "Clave-muy-larga-2026"},
        )
        self.assertRedirects(respuesta, reverse("cuentas:usuarios"))
        nuevo = User.objects.get(username="nuevo@ejemplo.cl")
        self.assertEqual(nuevo.perfil.corredora, self.andina)
        self.assertEqual(nuevo.perfil.rol, Perfil.Rol.AUDITOR)
        self.assertTrue(nuevo.check_password("Clave-muy-larga-2026"))
        self.assertTrue(Registro.objects.filter(operacion=Registro.Operacion.ADMINISTRACION).exists())

    def test_rechaza_clave_debil_y_correo_repetido(self):
        self.entrar(self.admin)
        respuesta = self.client.post(
            reverse("cuentas:usuarios"), {"correo": "ana", "nombre": "X", "rol": "ANALISTA", "clave": "123"}
        )
        self.assertEqual(respuesta.status_code, 200)
        self.assertEqual(User.objects.filter(first_name="X").count(), 0)

    def test_cambiar_el_perfil_de_un_usuario(self):
        self.entrar(self.admin)
        self.client.post(
            reverse("cuentas:usuario_cambiar", args=[self.analista.perfil.pk]),
            {"accion": "rol", "rol": "AUDITOR"},
        )
        self.analista.perfil.refresh_from_db()
        self.assertEqual(self.analista.perfil.rol, Perfil.Rol.AUDITOR)

    def test_desactivar_a_un_usuario(self):
        self.entrar(self.admin)
        self.client.post(
            reverse("cuentas:usuario_cambiar", args=[self.analista.perfil.pk]), {"accion": "desactivar"}
        )
        self.analista.refresh_from_db()
        self.assertFalse(self.analista.is_active)

    def test_no_puede_cambiarse_a_si_mismo(self):
        self.entrar(self.admin)
        self.client.post(
            reverse("cuentas:usuario_cambiar", args=[self.admin.perfil.pk]), {"accion": "desactivar"}
        )
        self.admin.refresh_from_db()
        self.assertTrue(self.admin.is_active)

    def test_no_puede_tocar_usuarios_de_otra_corredora(self):
        self.entrar(self.admin)
        respuesta = self.client.post(
            reverse("cuentas:usuario_cambiar", args=[self.ajeno.perfil.pk]), {"accion": "desactivar"}
        )
        self.assertEqual(respuesta.status_code, 403)
        self.ajeno.refresh_from_db()
        self.assertTrue(self.ajeno.is_active)
