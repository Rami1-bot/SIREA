"""
Genera el SQL para cambiar la contrasena de un administrador.

Uso (desde la carpeta del proyecto, con el entorno virtual activado):

    python resetear_password_admin.py

Te pide el usuario y la contrasena nueva (no se muestra al escribirla).
La contrasena NO se guarda ni se envia a ningun lado: el script solo
imprime una sentencia UPDATE con el hash bcrypt (de un solo sentido), que
pegas en el SQL Editor de Supabase. Usa la misma funcion de hash que la
aplicacion (src/security.py), asi el login funciona de inmediato.
"""
import getpass
import sys

from src.password_policy import generar, validar
from src.security import hash_password


def generar_sql(usuario: str, password: str, reactivar: bool = True) -> str:
    usuario_sql = usuario.replace("'", "''")
    nuevo_hash = hash_password(password)
    cambios = f"set password_hash = '{nuevo_hash}'" + (",\n    activo = true" if reactivar else "")
    return (
        "update public.administradores\n"
        f"{cambios}\n"
        f"where usuario = '{usuario_sql}'\n"
        "returning usuario, rol, activo;"
    )


def generar_valida(usuario: str) -> str:
    """Contraseña aleatoria que además cumple la política frente al usuario (no lo contiene, etc.)."""
    for _ in range(50):
        p = generar()
        if validar(p, contexto=[usuario])[0]:
            return p
    raise RuntimeError("No se pudo generar una contraseña válida; vuelva a intentarlo.")


def main() -> int:
    usuario = input("Usuario del administrador (ej. superadmin): ").strip()
    if not usuario:
        print("Debe indicar un usuario.")
        return 1

    print("La contraseña debe tener al menos 10 caracteres, mayúsculas, minúsculas, número y símbolo,")
    print("y no puede ser una contraseña común ni contener el usuario.")
    print("Si prefiere que el sistema genere una segura, deje el campo vacío y presione Enter.\n")
    password = getpass.getpass("Nueva contraseña (Enter para generar una): ")
    if not password:
        password = generar_valida(usuario)
        print(f"\nContraseña generada (anótela ahora; no se volverá a mostrar): {password}\n")
    else:
        valida, motivo = validar(password, contexto=[usuario])
        if not valida:
            print(motivo)
            return 1
        if getpass.getpass("Repita la contraseña: ") != password:
            print("Las contraseñas no coinciden.")
            return 1

    resp = input("¿Reactivar también la cuenta si estaba desactivada? (S/n): ").strip().lower()
    reactivar = resp not in ("n", "no")

    print("\n--- Pegue esto en el SQL Editor de Supabase y ejecútelo ---\n")
    print(generar_sql(usuario, password, reactivar))
    print("\n--- Debe devolver 1 fila. Si devuelve 0, el usuario no existe. ---")
    return 0


if __name__ == "__main__":
    sys.exit(main())
