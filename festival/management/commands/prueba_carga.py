"""Prueba de carga: muchos votantes votando a la vez contra la base de datos configurada."""
import random
import threading
import time

from django.conf import settings
from django.contrib.auth.models import User
from django.core.management.base import BaseCommand, CommandError
from django.db import connection, connections
from django.db.models import Count
from django.test import Client
from django.urls import reverse

from festival.models import Edicion, Votacion, Votante, Voto

# Solo los votantes creados por esta prueba usan este prefijo; así la limpieza nunca toca votantes reales.
USUARIO_PREFIJO = "carga_"


def _percentil(valores, p):
    if not valores:
        return 0.0
    ordenados = sorted(valores)
    return ordenados[min(len(ordenados) - 1, round(p / 100 * (len(ordenados) - 1)))]


class Command(BaseCommand):
    help = (
        "Simula muchos votantes votando a la vez (una votación abierta por categoría de la edición "
        "activa), repite todas las solicitudes para probar los duplicados y verifica los registros "
        "guardados en la base. Crea votantes temporales y los borra al terminar."
    )

    def add_arguments(self, parser):
        parser.add_argument("--votantes", type=int, default=200, help="Votantes simulados (por defecto 200).")
        parser.add_argument("--hilos", type=int, default=20, help="Hilos simultáneos (por defecto 20).")
        parser.add_argument("--conservar", action="store_true",
                            help="No borrar los votantes y votos de la prueba al terminar.")
        parser.add_argument("--forzar", action="store_true",
                            help="Permitir la prueba con DEBUG apagado (escribe votos en la base configurada).")

    def handle(self, *args, **opciones):
        if not settings.DEBUG and not opciones["forzar"]:
            raise CommandError("Esta prueba escribe votos en la base configurada. Usa --forzar si estás seguro.")
        cantidad = max(1, opciones["votantes"])
        hilos = max(1, min(opciones["hilos"], cantidad))

        edicion = Edicion.objects.filter(activa=True).first()
        if edicion is None:
            raise CommandError("No hay una edición activa. Ejecuta primero: python manage.py cargar_datos_prueba")
        abiertas = [v for v in Votacion.objects.filter(categoria__edicion=edicion).select_related("categoria")
                    if v.abierta]
        # Una votación por categoría: con la regla de unicidad solo se puede votar una vez por categoría.
        por_categoria = {}
        for votacion in abiertas:
            if votacion.opciones.filter(activa=True).exists():
                por_categoria.setdefault(votacion.categoria_id, votacion)
        votaciones = list(por_categoria.values())
        if not votaciones:
            raise CommandError("No hay votaciones abiertas con opciones en la edición activa.")
        opciones_por_votacion = {
            v.pk: list(v.opciones.filter(activa=True).values_list("pk", flat=True)) for v in votaciones
        }

        motor = connection.vendor
        self.stdout.write(f"Base de datos: {motor} · edición {edicion.anio} · {len(votaciones)} votaciones abiertas")
        if motor == "sqlite":
            self.stdout.write(self.style.WARNING(
                "SQLite no soporta bien escrituras simultáneas: espera errores de bloqueo. "
                "Usa MySQL para una prueba representativa."))

        self._limpiar()
        try:
            usuarios = self._crear_votantes(cantidad)
            esperado = len(usuarios) * len(votaciones)
            host = next((h for h in settings.ALLOWED_HOSTS if h and h != "*" and not h.startswith(".")), "localhost")

            self.stdout.write(f"\nFase 1: {len(usuarios)} votantes votan a la vez ({hilos} hilos)")
            ok1 = self._fase(usuarios, votaciones, opciones_por_votacion, hilos, host)
            total1 = self._contar()
            self.stdout.write(f"  Votos guardados: {total1} (esperados {esperado})")

            self.stdout.write("\nFase 2: los mismos votantes repiten todas las solicitudes (duplicados)")
            ok2 = self._fase(usuarios, votaciones, opciones_por_votacion, hilos, host)
            total2 = self._contar()
            duplicados = (
                Voto.objects.filter(votante__usuario__username__startswith=USUARIO_PREFIJO)
                .values("votante_id", "categoria_id").annotate(n=Count("id")).filter(n__gt=1).count()
            )
            cuarentena = Voto.objects.filter(
                votante__usuario__username__startswith=USUARIO_PREFIJO, en_cuarentena=True).count()
            self.stdout.write(f"  Votos guardados: {total2} (esperados {esperado})")

            self.stdout.write("\nVerificación en la base de datos")
            self.stdout.write(f"  Votos registrados:                    {total2} / {esperado}")
            self.stdout.write(f"  Pares votante-categoría duplicados:   {duplicados}")
            self.stdout.write(f"  Votos enviados a cuarentena:          {cuarentena}")
            aprobada = ok1 and ok2 and total1 == esperado and total2 == esperado and duplicados == 0
            if aprobada:
                self.stdout.write(self.style.SUCCESS("\nRESULTADO: correcto, sin duplicados ni errores."))
            else:
                self.stdout.write(self.style.ERROR("\nRESULTADO: hay diferencias o errores. Revisa el detalle anterior."))
        finally:
            if opciones["conservar"]:
                self.stdout.write("Se conservaron los votantes y votos de la prueba (usuarios \"carga_*\").")
            else:
                self._limpiar()
                self.stdout.write("Se borraron los votantes y votos de la prueba.")

    # ---------------------------------------------------------------- utilidades
    def _contar(self):
        return Voto.objects.filter(votante__usuario__username__startswith=USUARIO_PREFIJO).count()

    def _limpiar(self):
        Voto.objects.filter(votante__usuario__username__startswith=USUARIO_PREFIJO).delete()
        User.objects.filter(username__startswith=USUARIO_PREFIJO).delete()

    def _crear_votantes(self, cantidad):
        self.stdout.write(f"Creando {cantidad} votantes de prueba...")
        for i in range(cantidad):
            usuario = User(username=f"{USUARIO_PREFIJO}{i:06d}")
            usuario.set_unusable_password()
            usuario.save()
            Votante.objects.create(
                usuario=usuario, cedula=f"99{i:08d}", celular=f"39{i:08d}",
                mayor_edad_confirmada=True, datos_autorizados=True, verificado=True,
            )
        return list(User.objects.filter(username__startswith=USUARIO_PREFIJO).order_by("pk"))

    def _fase(self, usuarios, votaciones, opciones_por_votacion, hilos, host):
        latencias, estados, errores = [], {}, []
        candado = threading.Lock()
        grupos = [usuarios[i::hilos] for i in range(hilos)]

        def trabajo(grupo):
            lat, est, err = [], {}, []
            try:
                for usuario in grupo:
                    # Una IP distinta por votante, para no disparar la cuarentena por ráfagas de una sola IP.
                    cliente = Client(HTTP_HOST=host, REMOTE_ADDR=f"10.{(usuario.pk >> 8) & 255}.{usuario.pk & 255}.1")
                    cliente.force_login(usuario)
                    for votacion in votaciones:
                        url = reverse("festival:confirmar", args=[votacion.pk])
                        opcion = random.choice(opciones_por_votacion[votacion.pk])
                        inicio = time.perf_counter()
                        try:
                            respuesta = cliente.post(url, {"opcion": opcion})
                            est[respuesta.status_code] = est.get(respuesta.status_code, 0) + 1
                        except Exception as error:  # noqa: BLE001 - se reporta, no se detiene la prueba
                            err.append(repr(error)[:150])
                        lat.append(time.perf_counter() - inicio)
            finally:
                connections.close_all()
                with candado:
                    latencias.extend(lat)
                    errores.extend(err)
                    for codigo, n in est.items():
                        estados[codigo] = estados.get(codigo, 0) + n

        inicio = time.perf_counter()
        hilos_activos = [threading.Thread(target=trabajo, args=(g,)) for g in grupos if g]
        for hilo in hilos_activos:
            hilo.start()
        for hilo in hilos_activos:
            hilo.join()
        duracion = time.perf_counter() - inicio

        total = len(latencias)
        self.stdout.write(f"  Solicitudes: {total} en {duracion:.2f} s ({total / duracion:.1f} por segundo)" if duracion else "")
        self.stdout.write(
            f"  Latencia (ms): promedio {1000 * sum(latencias) / total:.0f} · "
            f"mediana {1000 * _percentil(latencias, 50):.0f} · "
            f"p95 {1000 * _percentil(latencias, 95):.0f} · "
            f"máxima {1000 * max(latencias):.0f}" if total else "  Sin solicitudes.")
        self.stdout.write(f"  Códigos de respuesta: {dict(sorted(estados.items()))}")
        if errores:
            self.stdout.write(self.style.ERROR(f"  Errores: {len(errores)} (ejemplo: {errores[0]})"))
        sin_errores = not errores and all(codigo < 500 for codigo in estados)
        return sin_errores
