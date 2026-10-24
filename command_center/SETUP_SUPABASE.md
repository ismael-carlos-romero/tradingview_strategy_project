# Command Center — instalación Supabase (MVP 0.1)
**Rama:** command-center · **Estado:** implementación sin desplegar.

## Preparación por Ismael
1. Crear un proyecto en https://supabase.com/dashboard con región adecuada y habilitar autenticación por email.
2. Desactivar registro público de usuarios (Auth > Providers > Email, confirmar que no se permita signup público); crear/invitar únicamente la cuenta autorizada desde el panel de administración. Activar MFA si está disponible.
3. Abrir SQL Editor y ejecutar `command_center/supabase_schema.sql`. Revisar que RLS esté activa en las siete tablas.
4. Copiar URL del proyecto y **publishable key** desde Settings > API. Son valores públicos por diseño. Reemplazar los marcadores en `command_center/config.js`; jamás usar `service_role` ni `sb_secret_`.
5. Probar primero con servidor local (por ejemplo el que Claude ya usa). Para publicar en GitHub Pages, Claude debe probar y fusionar la rama tras aprobación.

## Comportamiento esperado
- Sin Supabase configurado: interfaz muestra error de configuración; no simula datos reales.
- Sin sesión: pantalla de login; no hay lectura de tablas.
- Con sesión: datos reales filtrados por `owner_id = auth.uid()`.
- Sin registros: panel vacío y organigrama de referencia explícitamente marcado como NO DESPLEGADO.
- Bot apagado: última captura registrada; nunca interpretar un snapshot como estado en vivo.
- Oficina ARGOS: panel informativo; aún no hay procesos de auditoría desplegados.
- La pantalla es **solo lectura**. Los comandos no se crean desde el navegador en este MVP.

## Validación obligatoria antes de merge
1. Acceso anónimo: `select` a tablas `cc_*` debe fallar (no hay permiso anon).
2. Usuario autenticado A: puede leer solo sus filas. Usuario B no ve filas de A.
3. Usuario autenticado: `insert/update/delete` a tablas `cc_*` debe fallar.
4. Login incorrecto: error sin revelar detalles de credenciales.
5. Conexión fallida: error visible, nunca mostrar métricas ficticias.
6. Verificar que GitHub Pages no contiene claves de servicio, contraseñas ni datos operativos.
7. Confirmar que el bot local, el túnel y `INICIAR_MELIORA_OPTIONS.bat` no sufrieron modificaciones.

## Próximos pasos
- Claude revisa las migraciones en proyecto Supabase real y prueba login/RLS.
- Jarvis implementa integración en la navegación principal tras revisión de la interfaz.
- Claude construye sincronización desde PC con permisos mínimos y sin enviar secretos al frontend.
- Ejecutores de agentes en la nube son una fase separada: un panel accesible 24/7 no significa que agentes estén trabajando 24/7.

## Advertencia
`service_role` omite RLS. Todo proceso servidor que use credenciales privilegiadas debe validar identidad/propiedad, restringir tipos de comando y registrar eventos. No exponer una API de órdenes financieras a partir de la cola de comandos.
