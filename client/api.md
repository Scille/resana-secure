# Resana-Secure client (localhost server) API

## Liste des erreurs

Pour la suite de ce documents, les erreurs listées sous la forme:

> - HTTP \<CODE\>: `<error-name>`

correspondent à une réponse du type:
```python
HTTP <CODE>
{
    "error": "<error-name>"
}
```

Voici la liste des erreurs par ordre alphabétique:
- `archived_workspace` (HTTP 403)
- `archiving_not_allowed` (HTTP 403)
- `archiving_period_is_too_short` (HTTP 400)
- `authentication_requested` (HTTP 401)
- `bad_claimer_sas` (HTTP 400)
- `bad_data` (HTTP 400)
- `bad_greeter_sas` (HTTP 400)
- `bad_key` (HTTP 400)
- `cannot_delete_root_folder` (HTTP 400)
- `cannot_move_root_folder` (HTTP 400)
- `cannot_use_both_authentication_modes` (HTTP 400)
- `claimer_already_member` (HTTP 400)
- `claimer_not_a_member` (HTTP 400)
- `connection_refused_by_server` (HTTP 502)
- `deleted_workspace` (HTTP 410)
- `destination_parent_not_a_folder` (HTTP 400)
- `device_not_found` (HTTP 404)
- `email_not_in_recipients` (HTTP 400)
- `failed_to_disable_offline_availability` (HTTP 400)
- `failed_to_enable_offline_availability` (HTTP 400)
- `forbidden_workspace` (HTTP 403)
- `invalid_configuration` (HTTP 400)
- `invalid_passphrase` (HTTP 400)
- `invalid_state` (HTTP 409)
- `invitation_already_used` (HTTP 400)
- `invitation_not_found` (HTTP 400)
- `json_body_expected` (HTTP 400)
- `mountpoint_already_mounted` (HTTP 400)
- `mountpoint_not_mounted` (HTTP 404)
- `no_shamir_recovery_setup` (HTTP 400)
- `not_enough_shares` (HTTP 400)
- `not_a_file` (HTTP 404)
- `not_a_folder` (HTTP 404)
- `not_connected_to_rie` (HTTP 401)
- `not_found` (HTTP 404)
- `not_setup` (HTTP 404)
- `offline` (HTTP 503)
- `offline_availability_already_disabled` (HTTP 400)
- `offline_availability_already_enabled` (HTTP 400)
- `organization_already_bootstrapped` (HTTP 400)
- `precondition_failed` (HTTP 409)
- `read_only_workspace` (HTTP 403)
- `recipient_already_recovered` (HTTP 400)
- `sharing_not_allowed` (HTTP 403)
- `source_not_a_folder` (HTTP 404)
- `unexpected_error` (HTTP 400)
- `unknown_destination_parent` (HTTP 404)
- `unknown_email` (HTTP 404)
- `unknown_entry` (HTTP 404)
- `unknown_file` (HTTP 404)
- `unknown_folder` (HTTP 404)
- `unknown_organization` (HTTP 404)
- `unknown_parent` (HTTP 404)
- `unknown_source` (HTTP 404)
- `unknown_token` (HTTP 404)
- `unknown_workspace` (HTTP 404)
- `users_not_found` (HTTP 400)


Une erreur dans le formatage de la requête est retournée sous la forme suivante:

```python
HTTP 400
{
    "erreur": "bad_data",
    "fields": ["<field_name>", ...]
}
```

Une erreur non-attendue peut aussi être retournée sous la forme suivante:

```python
HTTP 400
{
    "erreur": "unexpected_error",
    "detail": "<some details about the error>"
}
```

## Pre-Authentification

### `GET <server-resana>/resana-secure/master-key`

Récupère la "encrypted master key RESANA Secure" depuis le serveur RESANA.

**Response:**


```python
HTTP 200
{
    "master-key": <base64>
}
```

**Erreurs:**

- HTTP 404: l'utilisateur ne possède pas de master-key

Une fois la "encrypted master key RESANA Secure" récupérée,
le client RESANA s'occupe de la déchiffrer via le mdp utilisateur RESANA Secure
(lui-même dérivé du mdp utilisateur global).

### `POST <server-resana>/auth/password`

Changement du mot de passe RESANA ainsi que de la master key RESANA Secure.

**Request:**


```python
{
    "old_password": <string>,
    "new_password": <string>,
    "new_resana_secure_master_key": <base64>
}
```

**Response:**


```python
HTTP 200
{
}
```

**Erreurs:**

- HTTP 409: le mot de passe a déjà été changé (i.e. `old_password` n'est pas le mot de passe actuel)

## Authentification

### `POST /auth`

Procède à l'authentification auprès du client Parsec.
Cette requête doit être réalisée en tout premier, elle fournit un cookie
de session permettant d'authentifier les autres requêtes.

**Request:**

Deux différentes options sont disponibles pour l'authentification :

- La première (historique) utilise la clef Parsec :

```python
{
    "organization": Optional<string>,
    "email": <string>,
    "key": <base64>
}
```

- La seconde utilise la clef Parsec chiffrée ainsi que le mot de passe utilisateur. Cette méthode d'authentification doit être utilisée au moins une fois avant de pouvoir se connecter en mode hors-ligne.

```python
{
    "organization": Optional<string>,
    "email": <string>,
    "encrypted_key": <base64>,
    "user_password": <string>
}
```

`email` correspondant à l'email utilisé lors de l'enrôlement RESANA Secure.

`user_password` doit être une chaîne de caractère échappé pour répondre aux normes json

**Response:**


```python
HTTP 200
Set-Cookie: session=<token>; HttpOnly; Path=/; SameSite=Strict
{
    "token": <token>
}
```

**Erreurs:**

- HTTP 404: `device_not_found`, le poste n'a pas été enrôlé pour cet utilisateur (i.e. il ne contient pas de fichier de clés de Device à déchiffrer)
- HTTP 400: `bad_key`, la clé de déchiffrement est invalide
- HTTP 400: `cannot_use_both_authentication_modes`, si les deux modes d'authentification sont utilisés simultanément

Une fois obtenu, le token d'authentification est

```raw
Authorization: Bearer <token>
```

Il est possible de s'authentifier auprès de plusieurs organisations, chaque
authentification retournant un token différent.

### `DELETE /auth`

Met fin à l'authentification auprès du client Parsec et invalide le token d'authentification.

**Response:**


```python
HTTP 200
Set-Cookie: session=; Expires=Thu, 01-Jan-1970 00:00:00 GMT; Max-Age=0; Path=/
{
}
```

### `DELETE /auth/all`

Met fin à toutes les authentifications auprès du client Parsec et invalide tous les tokens d'authentification.

**Response:**


```python
HTTP 200
{
}
```

### `POST /organization/bootstrap`

Le boostrap est la phase d'enregistrement du premier utilisateur d'une organisation
nouvellement créée.

**Request:**


```python
{
    "organization_url": <string>,
    "email": <string>,
    "key": <base64>,
    "sequester_verify_key": <string or null>,
}
```

Le champ `organization_url` contient une URL du type `parsec://parsec.example.com/my_org?action=bootstrap_organization&token=1234ABCD`.

`key` est utilisé pour chiffrer le fichier de clé de Device résultant de l'opération de bootstrap.

`sequester_verify_key` est un champ optionel devant être présent pour que l'organisation supporte le séquestre (non ultérieurement modifiable).
Il contient la partie publique de la clé RSA (au format PEM, c'est à dire base64 avec `-----BEGIN PUBLIC KEY-----` header/footer) de l'autorité
de séquestre.

**Response:**


```python
HTTP 200
{
}
```

**Erreurs:**

- HTTP 400: `organization_already_bootstrapped`
- HTTP 404: `unknown_organization`, l'organisation n'existe pas sur le serveur Parsec ou l'URL de bootstrap n'est pas valide
- HTTP 503: `offline`, le client Parsec n'a pas pu joindre le serveur Parsec (e.g. le poste client est hors-ligne)


## Utilisateurs & invitations

### [NOT IMPLEMENTED] `GET /humans?q=<query>&page=<int>&per_page=<int>&omit_revoked=<bool>`

`query` est recherchée contre les champs human_handle.email et human_handle.label, les matchs partiels sont acceptés.
(par exemple, `query=john` va matcher contre `email:john.doe@example.com` et contre `Bob Johnson`)

**Response:**


```python
HTTP 200
{
    "users": [
        {
            "user_id": <uuid>,
            "human_handle": {
                "email": <string>,
                "label": <string>
            },
            "profile": <string>,
            "created_on": <datetime>,
            "revoked_on": <datetime>
        },
        …
    ],
    "total": <int>
}
```

**Erreurs:**

- HTTP 503: `offline`, le client Parsec n'a pas pu joindre le serveur Parsec (e.g. le poste client est hors-ligne)
- HTTP 502: `connection_refused_by_server`, le client Parsec s'est vu refuser sa requête par le serveur Parsec (e.g. l'utilisateur Parsec a été révoqué)

`profile` peut être: `ADMIN` ou `STANDARD`

### `POST /humans/<email>/revoke`

**Request:**


```python
{
}
```

**Response:**


```python
HTTP 200
{
}
```

**Erreurs:**

- HTTP 404: si email inconnu
- HTTP 403: si l'utilisateur actuel n'a pas le profil administrateur sur l'organisation Parsec
- HTTP 503: `offline`, le client Parsec n'a pas pu joindre le serveur Parsec (e.g. le poste client est hors-ligne)
- HTTP 502: `connection_refused_by_server`, le client Parsec s'est vu refuser sa requête par le serveur Parsec (e.g. l'utilisateur Parsec a été révoqué)

### `GET /invitations`

Récupère la liste des invitations en cours.

**Response:**


```python
HTTP 200
{
    "users": [
        {
            "token": <uuid>,
            "created_on": <datetime>,
            "claimer_email": <string>,
            "status": <string>
        },
        …
    ],
    "device": <null> or {
            "token": <uuid>,
            "created_on" <datetime>,
            "status": <string>
        }
    "shamir_recoveries": [
        {
            "token": <uuid>,
            "created_on": <datetime>,
            "claimer_email": <string>,
            "status": <string>
        },
        …
    ]
}
```

**Erreurs:**

- HTTP 503: `offline`, le client Parsec n'a pas pu joindre le serveur Parsec (e.g. le poste client est hors-ligne)
- HTTP 502: `connection_refused_by_server`, le client Parsec s'est vu refuser sa requête par le serveur Parsec (e.g. l'utilisateur Parsec a été révoqué)

`status` peut être: `IDLE` ou `READY`

**Notes:**

- Le statut `READY` indique que la personne invitée s'est connectée au serveur Parsec
avec pour intention de procéder à l'enrôlement.
- Il ne peut y avoir que zéro ou une seule invitation de device à la fois.

### `POST /invitations`

Créé une nouvelle invitation.

**Request:**


```python
{
    "type": "user",
    "claimer_email": <string>
}
```

ou pour un device

```python
{
    "type": "device"
}
```

ou pour une récupération partagée
```python
{
    "type": "shamir_recovery"
    "claimer_email": <string>
}
```

**Response:**


```python
HTTP 200
{
    "token": <uuid>
}
```

**Erreurs:**

- HTTP 400: `claimer_already_member`
- HTTP 400: `claimer_not_a_member` (seulement pour les récupérations partagées)
- HTTP 400: `no_shamir_recovery_setup` (seulement pour les récupérations partagées)
- HTTP 403: si l'utilisateur actuel n'a pas le profil administrateur sur l'organisation Parsec et tente d'inviter un autre utilisateur.
- HTTP 503: `offline`, le client Parsec n'a pas pu joindre le serveur Parsec (e.g. le poste client est hors-ligne)
- HTTP 502: `connection_refused_by_server`, le client Parsec s'est vu refuser sa requête par le serveur Parsec (e.g. l'utilisateur Parsec a été révoqué)

La création d'invitation est idempotent (si une invitation existe déjà, elle ne sera pas recréée et le token existant sera retourné).

### `DELETE /invitations/<token>`

Supprime une invitation.

**Request:**


```python
{
}
```

**Response:**


```python
HTTP 204
{
}
```

**Erreurs:**

- HTTP 400: `invitation_already_used`
- HTTP 404: `unknown_token`, si le token n'existe pas
- HTTP 503: `offline`, le client Parsec n'a pas pu joindre le serveur Parsec (e.g. le poste client est hors-ligne)
- HTTP 502: `connection_refused_by_server`, le client Parsec s'est vu refuser sa requête par le serveur Parsec (e.g. l'utilisateur Parsec a été révoqué)

## Enrôlement (greeter)

### `POST /invitations/<token>/greeter/1-wait-peer-ready`

Démarre la phase d'enrôlement et attend que le pair à enrôler ait rejoint le serveur Parsec.

**Request:**


```python
{
}
```

**Response:**


```python
HTTP 200
{
    "type": <string>,
    "greeter_sas": <string>
}
```

**Erreurs:**

- HTTP 400: `invitation_already_used`
- HTTP 403 si l'utilisateur n'a pas le profil `ADMIN` et tente d'inviter un nouvel utilisateur
- HTTP 404: `unknown_token`, si le token n'existe pas
- HTTP 503: `offline`, le client Parsec n'a pas pu joindre le serveur Parsec (e.g. le poste client est hors-ligne)
- HTTP 502: `connection_refused_by_server`, le client Parsec s'est vu refuser sa requête par le serveur Parsec (e.g. l'utilisateur Parsec a été révoqué)
- HTTP 409: `invalid_state`, le processus d'invitation n'est pas dans l'état attendu pour exécuter cette commande

**Notes:**

- `type` est `DEVICE` ou `USER`
- `greeter_sas` est le code de 4 caractère à transmettre par un canal tiers au pair.

### `POST /invitations/<token>/greeter/2-wait-peer-trust`

Attend que le pair ait validé le code SAS qui lui a été fourni.

**Request:**


```python
{
}
```

**Response:**


```python
HTTP 200
{
    "candidate_claimer_sas": [<string>, …]
}
```

**Erreurs:**

- HTTP 403: si l'utilisateur n'a pas le profil `ADMIN` et tente d'inviter un nouvel utilisateur
- HTTP 404: `unknown_token`, si le token n'existe pas
- HTTP 503: `offline`, le client Parsec n'a pas pu joindre le serveur Parsec (e.g. le poste client est hors-ligne)
- HTTP 502: `connection_refused_by_server`, le client Parsec s'est vu refuser sa requête par le serveur Parsec (e.g. l'utilisateur Parsec a été révoqué)
- HTTP 409: `invalid_state`, si le pair a reset le processus (il faut repartir de la route `1-wait-peer-ready`)

`candidate_claimer_sas` est une liste de quatre codes dont un seul correspond
au code SAS du pair. L'utilisateur est donc obligé de se concerter avec le pair
pour déterminer lequel est le bon.

### `POST /invitations/<token>/greeter/3-check-trust`

Vérifie le code SAS fourni par le pair.

**Request:**


```python
{
    "claimer_sas": <string>
}
```

**Response:**


```python
HTTP 200
{
}
```

**Erreurs:**

- HTTP 403: si l'utilisateur n'a pas le profil `ADMIN` et tente d'inviter un nouvel utilisateur
- HTTP 404: `unknown_token`, si le token n'existe pas
- HTTP 400: `bad_claimer_sas` si le code SAS n'est pas bon
- HTTP 503: `offline`, le client Parsec n'a pas pu joindre le serveur Parsec (e.g. le poste client est hors-ligne)
- HTTP 502: `connection_refused_by_server`, le client Parsec s'est vu refuser sa requête par le serveur Parsec (e.g. l'utilisateur Parsec a été révoqué)
- HTTP 409: `invalid_state`, si le pair a reset le processus (il faut repartir de la route `1-wait-peer-ready`)

### `POST /invitations/<token>/greeter/4-finalize`

Ajoute le pair dans Parsec

**Request:**

pour un enrôlement de device:

```python
{
}
```

ou pour un enrôlement de user:

```python
{
    "claimer_email": <string>,
    "granted_profile": <string>
}
```

`granted_profile` peut être: `ADMIN` ou `STANDARD`
(seuls les profiles `ADMIN` peuvent à leur tour inviter de nouveaux utilisateurs)

**Response:**


```python
HTTP 200
{
}
```

**Erreurs:**

- HTTP 403: si l'utilisateur n'a pas le profil `ADMIN` et tente d'inviter un nouvel utilisateur
- HTTP 404: `unknown_token`, si le token n'existe pas
- HTTP 503: `offline`, le client Parsec n'a pas pu joindre le serveur Parsec (e.g. le poste client est hors-ligne)
- HTTP 502: `connection_refused_by_server`, le client Parsec s'est vu refuser sa requête par le serveur Parsec (e.g. l'utilisateur Parsec a été révoqué)
- HTTP 409: `invalid_state`, si le pair a reset le processus (il faut repartir de la route `1-wait-peer-ready`)

## Enrôlement (claimer)

### `POST /invitations/<token>/claimer/0-retrieve-info`

Démarre la phase d'enrôlement et récupère des informations de base sur l'invitation.

Note: this route is also exposed as `POST /invitations/<token>/claimer/0-retreive-info` due to a legacy typo (`0-retrieve-info` vs `0-retreive-info``)

**Request:**


```python
{
}
```

Les champs de la réponse dépendent de la valeur du champs `type`.

Pour une invitation de type utilisateur:

```python
HTTP 200
{
    "type": "user",
    "greeter_email": <string>
}
```

Pour une invitation de type device:

```python
HTTP 200
{
    "type": "device",
    "greeter_email": <string>
}
```

Pour une invitation de type shamir:

```python
HTTP 200
{
    "type": "shamir_recovery",
    "threshold": <int>,
    "enough_shares": <bool>,
    "recipients": [
        {
            "email": <str>,
            "weight": <int>,
            "retrieved": <bool>,
        },
        ...
    ]
}
```

Si `enough_share` est vrai, le client doit passer directement à l'étape 4.

**Erreurs:**

- HTTP 404: `unknown_token`, si le token n'existe pas
- HTTP 503: `offline`, le client Parsec n'a pas pu joindre le serveur Parsec (e.g. le poste client est hors-ligne)
- HTTP 502: `connection_refused_by_server`, le client Parsec s'est vu refuser sa requête par le serveur Parsec (e.g. l'utilisateur Parsec a été révoqué)
- HTTP 409: `invalid_state`, le processus d'invitation n'est pas dans l'état attendu pour exécuter cette commande

`type` est `device`, `user` or `shamir_recovery`
`candidate_greeter_sas` est une liste de quatre codes dont un seul correspond
au code SAS du pair. L'utilisateur est donc obligé de se concerter avec le pair
pour déterminer lequel est le bon.

### `POST /invitations/<token>/claimer/1-wait-peer-ready`

Attend que le pair qui enrôle ait rejoint le serveur Parsec.

**Request:**

Pour une invitation de type user ou device:

```python
{
}
```

Pour une invitation de type shamir

```python
{
    "greeter_email": str
}
```

**Response:**


```python
HTTP 200
{
    "candidate_greeter_sas": [<string>, …]
}
```

**Erreurs:**

- HTTP 400: `email_not_in_recipients`, dans le cas d'une invitation shamir, quand l'email fournit ne correspond à aucun des destinataires
- HTTP 400: `recipient_already_recovered`, dans le cas d'une invitation shamir, quand l'email fournit correspond à un destinataire déjà contacté
- HTTP 404: `unknown_token`, si le token n'existe pas
- HTTP 503: `offline`, le client Parsec n'a pas pu joindre le serveur Parsec (e.g. le poste client est hors-ligne)
- HTTP 502: `connection_refused_by_server`, le client Parsec s'est vu refuser sa requête par le serveur Parsec (e.g. l'utilisateur Parsec a été révoqué)
- HTTP 409: `invalid_state`, le processus d'invitation n'est pas dans l'état attendu pour exécuter cette commande

**Notes:**

- `type` est `DEVICE` ou `USER`
- `candidate_greeter_sas` est une liste de quatre codes dont un seul correspond au code SAS du pair.
  L'utilisateur est donc obligé de se concerter avec le pair pour déterminer lequel est le bon.

### `POST /invitations/<token>/claimer/2-check-trust`

Vérifie le code SAS fourni par le pair.

**Request:**


```python
{
    "greeter_sas": <string>
}
```

**Response:**


```python
HTTP 200
{
    "claimer_sas": <string>
}
```

**Erreurs:**

- HTTP 404: `unknown_token`, si le token n'existe pas
- HTTP 400: `bad_greeter_sas` si le code SAS n'est pas le bon
- HTTP 503: `offline`, le client Parsec n'a pas pu joindre le serveur Parsec (e.g. le poste client est hors-ligne)
- HTTP 502: `connection_refused_by_server`, le client Parsec s'est vu refuser sa requête par le serveur Parsec (e.g. l'utilisateur Parsec a été révoqué)
- HTTP 409: `invalid_state`, si le pair a reset le processus (il faut repartir de la route `1-wait-peer-ready`)

`greeter_sas` est le code de 4 caractère à transmettre par un canal tiers au pair.

### `POST /invitations/<token>/claimer/3-wait-peer-trust`

Attend que le pair ait validé le code SAS qui lui a été fourni.

**Request:**


```python
{
}
```

**Response:**


```python
HTTP 200
{
}
```

ou, dans le cadre d'une invitation de type shamir:

```python
HTTP 200
{
    "enough_shares": bool
}
```

Si `enough_shares` est faux, le client doit recommencer à l'étape 0 (ou directement l'étape 1) pour récupérer une nouvelle part du secret.

Si `enough_shares` est vrai, le client peut continuer à l'étape 4 pour finalizer la création de l'appareil.


**Erreurs:**

- HTTP 404: `unknown_token`, si le token n'existe pas
- HTTP 503: `offline`, le client Parsec n'a pas pu joindre le serveur Parsec (e.g. le poste client est hors-ligne)
- HTTP 502: `connection_refused_by_server`, le client Parsec s'est vu refuser sa requête par le serveur Parsec (e.g. l'utilisateur Parsec a été révoqué)
- HTTP 409: `invalid_state`, si le pair a reset le processus (il faut repartir de la route `1-wait-peer-ready`)


### `POST /invitations/<token>/claimer/4-finalize`

Ajoute le pair dans Parsec

**Request:**


```python
{
    "key": <base64>
}
```

**Response:**


```python
HTTP 200
{
}
```

**Erreurs:**

- HTTP 400: `not_enough_shares`, dans le cas d'une invitation shamir, avec un nombre de parts insuffisant
- HTTP 404: `unknown_token`, si le token n'existe pas
- HTTP 503: `offline`, le client Parsec n'a pas pu joindre le serveur Parsec (e.g. le poste client est hors-ligne)
- HTTP 502: `connection_refused_by_server`, le client Parsec s'est vu refuser sa requête par le serveur Parsec (e.g. l'utilisateur Parsec a été révoqué)
- HTTP 409: `invalid_state`, si le pair a reset le processus (il faut repartir de la route `1-wait-peer-ready`)

Note: `key` est utilisé pour chiffrer le fichier de clé de Device résultant de l'opération d'enrôlement.

## Workspace

### `GET /workspaces`

Récupère la liste des workspaces.

**Response:**


```python
HTTP 200
{
    "workspaces": [
        {
            "id": <uuid>,
            "name": <string>,
            "role": <string> = "OWNER", "MANAGER", "CONTRIBUTOR", "READER",
            "archiving_configuration": <string> = "AVAILABLE" | "ARCHIVED" | "DELETION_PLANNED"
        }
    ]
    …
}
```
​
Note: la configuration d'archivage peut-etre dans 3 états:

- Disponible (`AVAILABLE`): l'état par défaut, le workspace est disponible en lecture/écriture (si le role de l'utilisateur le permet).
- Archivé (`ARCHIVED`): le worspace est en lecture-seul jusqu'au prochain changement de configuration.
- Suppression planifié (`DELETION_PLANNED`): le workspace est en lecture-seul et une suppression de l'espace est planifié a une date donné.

Les workspaces en état archivé ou suppression planifié sont typiquement caché de la liste des workspaces à l'affichage.
Ils sont néamoins rendu disponible ici car leur accès peut etre nécéssaire dans des usages avancés:
- Changement de la configuration de l'archivage via `POST /workspaces/<id>/archiving`
- Accès aux données en lecture-seul lorsque l'utilisateur souhaite accédé au contenu du workspace malgré son archivage.

### `POST /workspaces`

Crée un nouveau workspace.
name : les caractères `\ / : * ? " > < |` sont interdits sur Windows https://learn.microsoft.com/en-us/windows/win32/fileio/naming-a-file ainsi que certains mots https://github.com/Scille/parsec-cloud/blob/77cc7ba287d442cc5b98366bf52cd1b51690db87/parsec/core/mountpoint/winify.py#L22-L43.

**Request:**


```python
{
    "name": <string>
}
```

**Response:**


```python
HTTP 201
{
    "id": <uuid>
}
```

**Notes:**

- Le nom d'un workspace n'a pas à être unique.
- La création d'un workspace peut se faire hors-ligne.

### `PATCH /workspaces/<id>`

Renomme un workspace.

**Request:**


```python
{
    "old_name": <string>,
    "new_name": <string>
}
```

**Response:**


```python
HTTP 200
{
}
```

**Erreurs:**

- HTTP 409: `precondition_failed`, le workspace a déjà eu son nom changé
- HTTP 404: `unknown_workspace`
- HTTP 410: `deleted_workspace`
- HTTP 403: `forbidden_workspace`

**Notes:**

- Le renommage d'un workspace n'impacte que l'utilisateur réalisant ce renommage (si le workspace est partagé avec d'autres utilisateurs, ceux-ci ne verront pas le changement de nom)

### `GET /workspaces/<id>/share`

Récupère les informations de partage d'un workspace. Un timestamp au format rfc3339 peut être fourni pour avoir les données à la date précisée.

**Request:**


```python
{
    "timestamp": Optional<string>
}
```

**Response:**


```python
HTTP 200
{
    "roles": {
        <email>: <role>
    }
}
```

**Erreurs:**

- HTTP 404: `unknown_workspace`
- HTTP 410: `deleted_workspace`
- HTTP 403: `forbidden_workspace`
- HTTP 503: `offline`, le client Parsec n'a pas pu joindre le serveur Parsec (e.g. le poste client est hors-ligne)
- HTTP 502: `connection_refused_by_server`, le client Parsec s'est vu refuser sa requête par le serveur Parsec (e.g. l'utilisateur Parsec a été révoqué)

### `PATCH /workspaces/<id>/share`

Partage un workspace.

**Request:**


```python
{
    "email": <string>,
    "role": <string ou null>
}
```

`role` peut être soit `null` (pour retirer le partage) soit une des strings: `OWNER`, `MANAGER`, `CONTRIBUTOR`, `READER`

**Response:**


```python
HTTP 200
{
}
```

**Erreurs:**

- HTTP 404: `unknown_workspace`
- HTTP 410: `deleted_workspace`
- HTTP 403: `forbidden_workspace`
- HTTP 403: `sharing_not_allowed`
- HTTP 404: `unknown_email`
- HTTP 503: `offline`, le client Parsec n'a pas pu joindre le serveur Parsec (e.g. le poste client est hors-ligne)
- HTTP 502: `connection_refused_by_server`, le client Parsec s'est vu refuser sa requête par le serveur Parsec (e.g. l'utilisateur Parsec a été révoqué)

**Notes:**

- le renommage d'un workspace n'impacte que l'utilisateur réalisant ce renommage (si le workspace est partagé avec d'autres utilisateurs, ceux-ci ne verront pas le changement de nom)


### `GET /workspaces/mountpoints`

Liste les workspaces montés

**Response:**


```python
HTTP 200
{
    "snapshots": [
        {
            "id": <string>,
            "name": <string>,
            "role": <string>
        }
    ],
    "workspaces": [
        {
            "id": <uuid>,
            "name": <string>,
            "role": <string>
        }
    ],
    …
}
```

**Notes:**

- `role` peut être: `OWNER`, `MANAGER`, `CONTRIBUTOR`, `READER`. Dans le cas des snapshot, le rôle sera toujours `READER`.


### `POST /workspaces/<id>/mount`

Monte un workspace en point de montage.

Deux options sont disponibles, la première sans argument pour un montage standard du workspace, la deuxième en spécifiant un timestamp en format rfc3339 pour monter le workspace dans l'état dans lequel il était à la date donnée.

Dans ce deuxième cas :

**Request:**


```python
{
    "timestamp": Optional<string>
}
```

**Response:**


```python
HTTP 200
{
    "id": <string>
    "timestamp": Optional<string>
}
```

**Erreurs:**

- HTTP 400: `mountpoint_already_mounted`
- HTTP 404: `unknown_workspace`
- HTTP 410: `deleted_workspace`
- HTTP 403: `forbidden_workspace`
- HTTP 401: `not_connected_to_rie`


### `POST /workspaces/<id>/unmount`

Démonte un workspace. S'il s'agit d'un workspace monté à une date donnée via un timestamp, ce même timestamp doit être fourni pour le démonter.

**Request:**


```python
{
    "timestamp": Optional<string>
}
```

**Response:**


```python
HTTP 200
{
}
```

**Erreurs:**

- HTTP 404: `mountpoint_not_mounted`
- HTTP 404: `unknown_workspace`
- HTTP 410: `deleted_workspace`
- HTTP 403: `forbidden_workspace`
- HTTP 401: `not_connected_to_rie`


### `POST /workspaces/<id>/toggle_offline_availability`

Active ou désactive la rémanence des données d'un workspace. Si désactivé, les fichiers seront téléchargés de manière paresseuse, uniquement lorsqu'une demande de consultation est faite. Si activé, tout est mis en oeuvre pour télécharger tous les fichiers présents dans le workspace afin qu'ils soient autant que possible disponibles même en étant hors-ligne.

**Request:**

```python
{
    "enable": <bool>
}
```

**Response:**


```python
HTTP 200
{
}
```

**Erreurs:**

- HTTP 404: `unknown_workspace`
- HTTP 410: `deleted_workspace`
- HTTP 403: `forbidden_workspace`
- HTTP 400: `offline_availability_already_disabled`
- HTTP 400: `offline_availability_already_enabled`
- HTTP 400: `failed_to_enable_offline_availability`
- HTTP 400: `failed_to_disable_offline_availability`
- HTTP 401: `not_connected_to_rie`


### `GET /workspaces/<id>/get_offline_availability_status`

Récupère des informations sur l'état de la disponibilité hors-ligne de ce workspace.

**Request:**

```python
{
}
```

**Response:**


```python
HTTP 200
{
    "is_running": <bool>,
    "is_prepared": <bool>,
    "is_available_offline": <bool>,
    "total_size": <int>,
    "remote_only_size": <int>,
    "local_and_remote_size": <int>,
}
```

**Erreurs:**

- HTTP 404: `unknown_workspace`
- HTTP 410: `deleted_workspace`
- HTTP 403: `forbidden_workspace`
- HTTP 401: `not_connected_to_rie`


## Archivage et suppression des workspaces

La configuration d'archivage/suppression peut-être dans 3 états:
- Disponible (`AVAILABLE`): l'état par défaut, le workspace est disponible en lecture/écriture (si le role de l'utilisateur le permet).e
- Archivé (`ARCHIVED`): le workspace est en lecture-seul jusqu'au prochain changement de configuration.
- Suppression planifié (`DELETION_PlANNED`): le workspace est en lecture-seul et une suppression de l'espace est planifié a une date donné.

### `GET /workspaces/<id>/archiving`

Récupère les informations sur l'état de l'archivage/suppression pour ce workspace.

En plus de l'état de la configuration courante, 4 informations sont fournis:
- La date de la configuration courante (`configured_on`). Elle peut être `null` si le workspace n'a jamais été configuré.
- L'email de l'utilisateur responsable de la configuration courante (`configured_by`). Elle peut être `null` si le workspace n'a jamais été configuré.
- La date de suppression planifiée (`deletion_date`). Elle n'est fourni que dans l'état de suppression planifié. Elle peut être déjà passée.
- Un booléen indiquant que le workspace est effectivement supprimé. Cela signifie que la date courante a dépassé la date de suppression planifié.
- La période d'archivage minimale en secondes (`minimum_archiving_period`). C'est la période minimale à respecter lors d'une suppression planifiée.

**Request:**

```python
{
}
```

**Response:**


```python
HTTP 200
{
    "configuration": <str> = "AVAILABLE" | "ARCHIVED" | "DELETION_PlANNED",
    "configured_on": <datetime or null>,
    "configured_by": <str or null>,
    "deletion_date": <datetime or null>,
    "minimum_archiving_period": <int> # in seconds
}
```

**Erreurs:**

- HTTP 404: `unknown_workspace`
- HTTP 410: `deleted_workspace`
- HTTP 403: `forbidden_workspace`

### `POST /workspaces/<id>/archiving`

Configure l'archivage ou planifie une suppression pour ce workspace.

**Notes:**

- La date de suppression (`deletion_date`) n'est fourni que dans le cas d'une suppression planifiée.
- Cette date de suppression doit respecter le délai d'archivage minimum, configuré au niveau de l'organization.
- Les droits de propriétaire (`OWNER`) sont nécessaires pour réaliser cette opération.

**Request:**

```python
{
    "configuration": <str> = "AVAILABLE" | "ARCHIVED" | "DELETION_PlANNED",
    "deletion_date": <datetime or null>,
}
```

**Response:**


```python
HTTP 200
{
}
```

**Erreurs:**

- HTTP 404: `unknown_workspace`
- HTTP 403: `archiving_not_allowed`
- HTTP 410: `deleted_workspace`
- HTTP 403: `forbidden_workspace`
- HTTP 400: `archiving_period_is_too_short`
- HTTP 502: `connection_refused_by_server`, le client Parsec s'est vu refuser sa requête par le serveur Parsec (e.g. l'utilisateur Parsec a été révoqué)


## Dossiers

### `GET /workspaces/<id>/folders`

Consulter l'arborescence d'un workspace. Un timestamp au format rfc3339 peut être fourni pour avoir les données à la date précisée.

**Request:**

```python
{
    "timestamp": Optional<string>
}
```

**Response:**


```python
HTTP 200
{
    "id": <uuid>,
    "name": <string>,
    "created": <datetime>,
    "updated": <datetime>,
    "type": "folder",
    "children": {
        <string>: {
            "id": <uuid>,
            "name": <string>,
            "created": <datetime>,
            "updated": <datetime>,
            "children": {…}
        },
        …
    }
}
```

**Erreurs:**

- HTTP 404: `unknown_workspace`
- HTTP 410: `deleted_workspace`
- HTTP 403: `forbidden_workspace`
- HTTP 503: `offline`, le client Parsec n'a pas pu joindre le serveur Parsec (e.g. le poste client est hors-ligne et le chemin à accéder n'est pas dans le cache local)

### `POST /workspaces/<id>/folders`

Créé un nouveau répertoire.
name : les caractères `\ / : * ? " > < |` sont interdits sur Windows https://learn.microsoft.com/en-us/windows/win32/fileio/naming-a-file ainsi que certains mots https://github.com/Scille/parsec-cloud/blob/77cc7ba287d442cc5b98366bf52cd1b51690db87/parsec/core/mountpoint/winify.py#L22-L43.

**Request:**


```python
{
    "name": <string>,
    "parent": <id>
}
```

**Response:**


```python
HTTP 201
{
    "id": <id>
}
```


**Erreurs:**

- HTTP 404: `unknown_workspace`
- HTTP 410: `deleted_workspace`
- HTTP 403: `forbidden_workspace`
- HTTP 403: `archived_workspace`
- HTTP 404: `unknown_parent`
- HTTP 503: `offline`, le client Parsec n'a pas pu joindre le serveur Parsec (e.g. le poste client est hors-ligne et le chemin à accéder n'est pas dans le cache local)

### `POST /workspaces/<id>/folders/rename`

Déplace/renomme un repertoire.

**Request:**


```python
{
    "id": <id>
    "new_name": <string>,
    "new_parent": <id or null>
}
```

**Response:**


```python
HTTP 200
{
}
```


**Erreurs:**

- HTTP 404: `unknown_workspace`
- HTTP 410: `deleted_workspace`
- HTTP 403: `archived_workspace`
- HTTP 403: `forbidden_workspace`
- HTTP 400: `destination_parent_not_a_folder`
- HTTP 400: `source_not_a_folder`
- HTTP 400: `cannot_move_root_folder`
- HTTP 404: `unknown_source_folder`
- HTTP 404: `unknown_destination_parent_folder`
- HTTP 403: si l'utilisateur n'a pas le profil `OWNER`/`MANAGER`/`CONTRIBUTER` sur le workspace
- HTTP 503: `offline`, le client Parsec n'a pas pu joindre le serveur Parsec (e.g. le poste client est hors-ligne et le chemin à accéder n'est pas dans le cache local)

### `DELETE /workspaces/<id>/folders/<id>`

Supprime un répertoire.

**Request:**


```python
{
}
```

**Response:**


```python
HTTP 204
{
}
```

ou

- HTTP 404: `unknown_workspace`
- HTTP 410: `deleted_workspace`
- HTTP 403: `forbidden_workspace`
- HTTP 400: `cannot_delete_root_folder`
- HTTP 403: `read_only_workspace`
- HTTP 403: `archived_workspace`
- HTTP 404: `not_a_folder`
- HTTP 404: `unknown_folder`
- HTTP 503: `offline`, le client Parsec n'a pas pu joindre le serveur Parsec (e.g. le poste client est hors-ligne et le chemin à accéder n'est pas dans le cache local)

## Fichiers

### `GET /workspaces/<id>/files/<folder_id>`

Consulte l'arborescence des fichiers d'un workspace. Un timestamp au format rfc3339 peut être fourni pour avoir les données à la date précisée.

**Request:**

```python
{
    "timestamp": Optional<string>
}
```

**Response:**


```python
HTTP 200
{
    "files": [
        {
            "id": <uuid>,
            "name": <string>,
            "extension": <string>,
            "size": <int>,
            "created": <datetime>,
            "created_by": <string>,
            "updated": <datetime>,
            "updated_by": <string>,
        },
        ...
    ]
}
```

**Erreurs:**

- HTTP 404: `unknown_workspace`
- HTTP 410: `deleted_workspace`
- HTTP 403: `forbidden_workspace`
- HTTP 404: `unknown_path`
- HTTP 503: `offline`, le client Parsec n'a pas pu joindre le serveur Parsec (e.g. le poste client est hors-ligne et le chemin à accéder n'est pas dans le cache local)


### `POST /workspaces/<id>/files`

Créé un nouveau fichier.
name/filename : les caractères `\ / : * ? " > < |` sont interdits sur Windows https://learn.microsoft.com/en-us/windows/win32/fileio/naming-a-file ainsi que certains mots https://github.com/Scille/parsec-cloud/blob/77cc7ba287d442cc5b98366bf52cd1b51690db87/parsec/core/mountpoint/winify.py#L22-L43.

**Request:**


En multipart (recommandé)

```python
HTTP multipart form-data avec
    name="parent" <ID_PARENT>
    name="file"; filename="<NOM_DU_FICHIER>" <CONTENU_DU_FICHIER>
```

ou en base64 en JSON (déprécié)

```python
{
    "name": <string>,
    "parent": <id>,
    "content": <base64>
}
```

**Response:**


```python
HTTP 201
{
    "id": <id>
}
```

**Erreurs:**

- HTTP 404: `unknown_workspace`
- HTTP 403: `archived_workspace`
- HTTP 410: `deleted_workspace`
- HTTP 403: `forbidden_workspace`
- HTTP 404: `unknown_path`
- HTTP 503: `offline`, le client Parsec n'a pas pu joindre le serveur Parsec (e.g. le poste client est hors-ligne et le chemin à accéder n'est pas dans le cache local)


### `POST /workspaces/<id>/files/rename`

Déplace/renomme un fichier

**Request:**


```python
{
    "id": <id>
    "new_name": <string>,
    "new_parent": <id or null>
}
```

**Response:**


```python
HTTP 200
{
}
```

**Erreurs:**

- HTTP 404: `unknown_workspace`
- HTTP 403: `archived_workspace`
- HTTP 410: `deleted_workspace`
- HTTP 403: `forbidden_workspace`
- HTTP 400: `invalid_destination`
- HTTP 404: `unknown_path`
- HTTP 503: `offline`, le client Parsec n'a pas pu joindre le serveur Parsec (e.g. le poste client est hors-ligne et le chemin à accéder n'est pas dans le cache local)


### `DELETE /workspaces/<id>/files/<id>`

Supprime un fichier.

**Request:**


```python
{
}
```

**Response:**


```python
HTTP 204
{
}
```

**Erreurs:**

- HTTP 404: `unknown_workspace`
- HTTP 410: `deleted_workspace`
- HTTP 403: `forbidden_workspace`
- HTTP 404: `unknown_entry`
- HTTP 404: `not_a_file`
- HTTP 503: `offline`, le client Parsec n'a pas pu joindre le serveur Parsec (e.g. le poste client est hors-ligne et le chemin à accéder n'est pas dans le cache local)

### `POST /workspaces/<id>/open/<id>`

Ouvre un fichier/répertoire. Un timestamp au format rfc3339 peut être fourni pour ouvrir le fichier dans l'état dans lequel il se trouvait à la date précisée.

**Request:**


```python
{
    "timestamp": Optional<string>
}
```

**Response:**


```python
HTTP 200
{
}
```

**Erreurs:**

- HTTP 404: `unknown_workspace`
- HTTP 410: `deleted_workspace`
- HTTP 403: `forbidden_workspace`
- HTTP 404: `unknown_file`
- HTTP 503: `offline`, le client Parsec n'a pas pu joindre le serveur Parsec (e.g. le poste client est hors-ligne)


### `POST /workspaces/<id>/search`

Un timestamp au format rfc3339 peut être fourni pour avoir les données à la date précisée.

**Request:**

```python
{
    "string": <string>,
    "case_sensitive": <bool> = false,
    "exclude_folders": <bool> = false
    "timestamp": Optional<string>
}
```

Reponse:
```python
HTTP 200
{
    "files": [
        {
            "id": <uuid>,
            "name": <string>,
            "path": <string>,
            "extension": <string>,
            "type": <string> = "folder" | "file",
            "size": <int>,
            "created": <datetime>,
            "updated": <datetime>,
        },
        ...
    ]
}
```

**Erreurs:**

- HTTP 404: `unknown_workspace`
- HTTP 410: `deleted_workspace`
- HTTP 403: `forbidden_workspace`


### [NOT IMPLEMENTED] `GET /workspaces/<id>/reencryption`

Récupère les information de rechiffrement du workspace.

**Response:**


```python
HTTP 200
{
    "need_reencryption": <boolean>,
    "user_revoked": [<string>, …],
    "role_revoked": [<string>, …],
    "reencryption_already_in_progress": <boolean>
}
```

**Erreurs:**

- HTTP 404: `unknown_workspace`
- HTTP 410: `deleted_workspace`
- HTTP 403: `forbidden_workspace`
- HTTP 404: `unknown_path`
- HTTP 503: `offline`, le client Parsec n'a pas pu joindre le serveur Parsec (e.g. le poste client est hors-ligne)

**Notes:**

- `user_revoked` liste des email des HumanHandle dont le user a été révoqué
- `role_revoked` liste des email des HumanHandle dont le user a perdu l'accès au workspace
- `reencryption_already_in_progress` le rechiffrement est déjà en cours


### [NOT IMPLEMENTED] `POST /workspaces/<id>/reencryption`

Lance le rechiffrement du workspace.

**Request:**


```python
{
}
```

**Response:**


```python
HTTP 200
{
}
```

**Erreurs:**

- HTTP 404: `unknown_workspace`
- HTTP 410: `deleted_workspace`
- HTTP 403: `forbidden_workspace`
- HTTP 403 si l'utilisateur n'a pas le profil `OWNER` sur le workspace
- HTTP 503: `offline`, le client Parsec n'a pas pu joindre le serveur Parsec (e.g. le poste client est hors-ligne)


## Récupération d'appareil

### `POST /recovery/export`

Créé un fichier de récupération pour le device authentifié.
Ce fichier de récupération sert à créer de nouveaux devices pour l'utilisateur, cela permet
notamment de récupérer son compte en cas de perte de son ordinateur ou bien d'oubli
de mot de passe.

**Request:**


```python
{
}
```

**Response:**


```python
HTTP 200
{
    "file_content": <base64>,
    "file_name": <string>,
    "passphrase": <string>
}
```

Le fichier doit être téléchargé par l'utilisateur et stocké dans un endroit limitant
les risques de pertes.
La passphrase doit être affichée à l'utilisateur et celui-ci doit être invité à stocker
la passphrase dans un endroit sûr et non accessible par un tiers.

### `POST /recovery/import`

Créé un nouveau device à partir du fichier de récupération généré préalablement.

**Request:**


```python
{
    "recovery_device_file_content": <base64>
    "recovery_device_passphrase": <string>
    "new_device_key": <string>
}
```

**Response:**


```python
HTTP 200
{
}
```

**Erreurs:**

- HTTP 400: `invalid_passphrase`


### `POST /recovery/shamir/setup`

Configure un nouvel appareil de récupération partagé.

**Request:**


```python
{
    "threshold": <int>
    "recipients": [
        {
            "email": <str>,
            "weight": <int>
        },
        ...
    ]
}
```

**Response:**


```python
HTTP 200
{
}
```

**Erreurs spécifiques:**

```python
HTTP 400
{
    "error": "users_not_found",
    "emails": [<string>, ...]
}
```


**Erreurs:**

- HTTP 400: `invalid_configuration`


### `DELETE /recovery/shamir/setup`

Supprime l'appareil de récupération partagé courant.

**Request:**


```python
{
}
```

**Response:**


```python
HTTP 200
{
}
```

### `GET /recovery/shamir/setup`

Retourne l'appareil de récupération partagé courant

```python
{
}
```

**Response:**


```python
HTTP 200
{
    "device_label": str,
    "threshold": int,
    "recipients": [
        {
            "email": <str>,
            "weight": <int>
        },
        ...
    ]
}
```

**Erreurs:**

- HTTP 404: `not_setup`


### `GET /recovery/shamir/setup/others`

Retourne l'appareil de récupération partagé courant

```python
{
}
```

**Response:**


```python
HTTP 200
{
    "setups": [
        {
            "email": <str>,
            "label": <str>,
            "device_label": <str>,
            "threshold": <int>,
            "recipients": [
                {
                    "email": <str>,
                    "weight": <int>
                },
            "my_weight": <int>,
        },
        ...
    ]
}
```
