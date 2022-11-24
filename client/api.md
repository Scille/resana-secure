# Resana-Secure client (localhost server) API

## Pre-Authentification

### `GET <server-resana>/resana-secure/master-key`

Récupère la "encrypted master key RESANA Secure" depuis le serveur RESANA.

Response:

```python
HTTP 200
{
    "master-key": <base64>
}
```

ou

- HTTP 404: l'utilisateur ne possède pas de master-key

Une fois la "encrypted master key RESANA Secure" récupérée,
le client RESANA s'occupe de la déchiffrer via le mdp utilisateur RESANA Secure
(lui-même dérivé du mdp utilisateur global).

### `POST <server-resana>/auth/password`

Changement du mot de passe RESANA ainsi que de la master key RESANA Secure.

Request:

```python
{
    "old_password": <string>,
    "new_password": <string>,
    "new_resana_secure_master_key": <base64>
}
```

Response:

```python
HTTP 200
{
}
```

ou

- HTTP 409: le mot de passe a déjà été changé (i.e. `old_password` n'est pas le mot de passe actuel)

## Authentification

### `POST /auth`

Procède à l'authentification auprès du client Parsec.
Cette requête doit être réalisée en tout premier, elle fournit un cookie
de session permettant d'authentifier les autres requêtes.

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

Response:

```python
HTTP 200
Set-Cookie: session=<token>; HttpOnly; Path=/; SameSite=Strict
{
    "token": <token>
}
```

ou

- HTTP 404: le poste n'a pas été enrôlé pour cet utilisateur (i.e. il ne contient pas de fichier de clés de Device à déchiffrer)
- HTTP 400: la clé de déchiffrement est invalide

Une fois obtenu, le token d'authentification est

```raw
Authorization: Bearer <token>
```

Il est possible de s'authentifier auprès de plusieurs organisations, chaque
authentification retournant un token différent.

### `DELETE /auth`

Met fin à l'authentification auprès du client Parsec et invalide le token d'authentification.

Response:

```python
HTTP 200
Set-Cookie: session=; Expires=Thu, 01-Jan-1970 00:00:00 GMT; Max-Age=0; Path=/
{
}
```

### `POST /organization/bootstrap`

Le boostrap est la phase d'enregistrement du premier utilisateur d'une organisation
nouvellement créée.

Request:

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

Response:

```python
HTTP 200
{
}
```

ou

```python
HTTP 400
{
    "error": "organization_already_boostrapped"
}
```

- HTTP 404: L'organisation n'existe pas sur le serveur Parsec ou l'URL de bootstrap n'est pas valide
- HTTP 503: le client Parsec n'a pas pu joindre le serveur Parsec (e.g. le poste client est hors-ligne)
- HTTP 502: le client Parsec s'est vu refuser sa requête par le serveur Parsec (e.g. l'organisation n'existe pas sure le serveur)

## Utilisateurs & invitations

### [NOT IMPLEMENTED] `GET /humans?q=<query>&page=<int>&per_page=<int>&omit_revoked=<bool>`

`query` est recherchée contre les champs human_handle.email et human_handle.label, les matchs partiels sont acceptés.
(par exemple, `query=john` va matcher contre `email:john.doe@example.com` et contre `Bob Johnson`)

Response:

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

ou

- HTTP 503: le client Parsec n'a pas pu joindre le serveur Parsec (e.g. le poste client est hors-ligne)
- HTTP 502: le client Parsec s'est vu refuser sa requête par le serveur Parsec (e.g. l'utilisateur Parsec a été révoqué)

`profile` peut être: `ADMIN` ou `STANDARD`

### `POST /humans/<email>/revoke`

Request:

```python
{
}
```

Response:

```python
HTTP 200
{
}
```

ou

- HTTP 404 si email inconnu
- HTTP 403 si l'utilisateur actuel n'a pas le profil administrateur sur l'organisation Parsec
- HTTP 503: le client Parsec n'a pas pu joindre le serveur Parsec (e.g. le poste client est hors-ligne)
- HTTP 502: le client Parsec s'est vu refuser sa requête par le serveur Parsec (e.g. l'utilisateur Parsec a été révoqué)

### `GET /invitations`

Récupère la liste des invitations en cours.

Response:

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
}
```

ou

- HTTP 503: le client Parsec n'a pas pu joindre le serveur Parsec (e.g. le poste client est hors-ligne)
- HTTP 502: le client Parsec s'est vu refuser sa requête par le serveur Parsec (e.g. l'utilisateur Parsec a été révoqué)

`status` peut être: `IDLE` ou `READY`

**Notes:**

- Le statut `READY` indique que la personne invitée s'est connectée au serveur Parsec
avec pour intention de procéder à l'enrôlement.
- Il ne peut y avoir que zéro ou une seule invitation de device à la fois.

### `POST /invitations`

Créé une nouvelle invitation.

Request:

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

Response:

```python
HTTP 200
{
    "token": <uuid>
}
```

ou

```python
HTTP 400
{
    "error":  "claimer_already_member"
}
```

ou

- HTTP 403 si l'utilisateur actuel n'a pas le profil administrateur sur l'organisation Parsec et tente d'inviter un autre utilisateur.
- HTTP 503: le client Parsec n'a pas pu joindre le serveur Parsec (e.g. le poste client est hors-ligne)
- HTTP 502: le client Parsec s'est vu refuser sa requête par le serveur Parsec (e.g. l'utilisateur Parsec a été révoqué)

La création d'invitation est idempotent (si une invitation existe déjà, elle ne sera pas recréée et le token existant sera retourné).

### `DELETE /invitations/<token>`

Supprime une invitation.

Request:

```python
{
    "token": <uuid>
}
```

Response:

```python
HTTP 204
{
}
```

ou

```python
HTTP 400
{
    "error": "invitation_already_used"
}
```

ou

- HTTP 404 si le token n'existe pas
- HTTP 503: le client Parsec n'a pas pu joindre le serveur Parsec (e.g. le poste client est hors-ligne)
- HTTP 502: le client Parsec s'est vu refuser sa requête par le serveur Parsec (e.g. l'utilisateur Parsec a été révoqué)

## Enrôlement (greeter)

### `POST /invitations/<token>/greeter/1-wait-peer-ready`

Démarre la phase d'enrôlement et attend que le pair à enrôler ait rejoint le serveur Parsec.

Request:

```python
{
}
```

Response:

```python
HTTP 200
{
    "type": <string>,
    "greeter_sas": <string>
}
```

ou

```python
HTTP 400
{
    "error": "invitation_already_used"
}
```

ou

- HTTP 403 si l'utilisateur n'a pas le profil `ADMIN` et tente d'inviter un nouvel utilisateur
- HTTP 404 si le token est inconnu
- HTTP 503: le client Parsec n'a pas pu joindre le serveur Parsec (e.g. le poste client est hors-ligne)
- HTTP 502: le client Parsec s'est vu refuser sa requête par le serveur Parsec (e.g. l'utilisateur Parsec a été révoqué)

`type` est `DEVICE` ou `USER`
`greeter_sas` est le code de 4 caractère à transmettre par un canal tiers au pair.

### `POST /invitations/<token>/greeter/2-wait-peer-trust`

Attend que le pair ait validé le code SAS qui lui a été fourni.

Request:

```python
{
}
```

Response:

```python
HTTP 200
{
    "candidate_claimer_sas": [<string>, …]
}
```

ou

- HTTP 403 si l'utilisateur n'a pas le profil `ADMIN` et tente d'inviter un nouvel utilisateur
- HTTP 404 si le token est inconnu
- HTTP 409 si le pair a reset le processus (il faut repartir de la route `1-wait-peer-ready`)
- HTTP 503: le client Parsec n'a pas pu joindre le serveur Parsec (e.g. le poste client est hors-ligne)
- HTTP 502: le client Parsec s'est vu refuser sa requête par le serveur Parsec (e.g. l'utilisateur Parsec a été révoqué)

`candidate_claimer_sas` est une liste de quatre codes dont un seul correspond
au code SAS du pair. L'utilisateur est donc obligé de se concerter avec le pair
pour déterminer lequel est le bon.

### `POST /invitations/<token>/greeter/3-check-trust`

Vérifie le code SAS fourni par le pair.

Request:

```python
{
    "claimer_sas": <string>
}
```

Response:

```python
HTTP 200
{
}
```

ou

- HTTP 403 si l'utilisateur n'a pas le profil `ADMIN` et tente d'inviter un nouvel utilisateur
- HTTP 404 si le token est inconnu
- HTTP 400 si claimer_sas n'est pas le bon
- HTTP 409 si le pair a reset le processus (il faut repartir de la route `1-wait-peer-ready`)
- HTTP 503: le client Parsec n'a pas pu joindre le serveur Parsec (e.g. le poste client est hors-ligne)
- HTTP 502: le client Parsec s'est vu refuser sa requête par le serveur Parsec (e.g. l'utilisateur Parsec a été révoqué)

### `POST /invitations/<token>/greeter/4-finalize`

Ajoute le pair dans Parsec

Request:
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

Response:

```python
HTTP 200
{
}
```

ou

- HTTP 403 si l'utilisateur n'a pas le profil `ADMIN` et tente d'inviter un nouvel utilisateur
- HTTP 404 si le token est inconnu
- HTTP 409 si le pair a reset le processus (il faut repartir de la route `1-wait-peer-ready`)
- HTTP 503: le client Parsec n'a pas pu joindre le serveur Parsec (e.g. le poste client est hors-ligne)
- HTTP 502: le client Parsec s'est vu refuser sa requête par le serveur Parsec (e.g. l'utilisateur Parsec a été révoqué)

## Enrôlement (claimer)

### `POST /invitations/<token>/claimer/0-retreive-info`

Démarre la phase d'enrôlement et récupère des informations de base sur l'invitation.

Request:

```python
{
    "token": <uuid>
}
```

Response:

```python
HTTP 200
{
    "type": <string>,
    "greeter_email": <string>,
}
```

ou

- HTTP 404 si le token est inconnu
- HTTP 503: le client Parsec n'a pas pu joindre le serveur Parsec (e.g. le poste client est hors-ligne)
- HTTP 502: le client Parsec s'est vu refuser sa requête par le serveur Parsec (e.g. l'utilisateur Parsec a été révoqué)

`type` est `DEVICE` ou `USER`
`candidate_greeter_sas` est une liste de quatre codes dont un seul correspond
au code SAS du pair. L'utilisateur est donc obligé de se concerter avec le pair
pour déterminer lequel est le bon.

### `POST /invitations/<token>/claimer/1-wait-peer-ready`

Attend que le pair qui enrôle ait rejoint le serveur Parsec.

Request:

```python
{
    "token": <uuid>
}
```

Response:

```python
HTTP 200
{
    "candidate_greeter_sas": [<string>, …]
}
```

ou

- HTTP 404 si le token est inconnu
- HTTP 503: le client Parsec n'a pas pu joindre le serveur Parsec (e.g. le poste client est hors-ligne)
- HTTP 502: le client Parsec s'est vu refuser sa requête par le serveur Parsec (e.g. l'utilisateur Parsec a été révoqué)

`type` est `DEVICE` ou `USER`
`candidate_greeter_sas` est une liste de quatre codes dont un seul correspond
au code SAS du pair. L'utilisateur est donc obligé de se concerter avec le pair
pour déterminer lequel est le bon.

### `POST /invitations/<token>/claimer/2-check-trust`

Vérifie le code SAS fourni par le pair.

Request:

```python
{
    "greeter_sas": <string>
}
```

Response:

```python
HTTP 200
{
    "claimer_sas": <string>
}
```

ou

- HTTP 404 si le token est inconnu
- HTTP 400 si greeter_sas n'est pas le bon
- HTTP 409 si le pair a reset le processus (il faut repartir de la route `1-wait-peer-ready`)
- HTTP 503: le client Parsec n'a pas pu joindre le serveur Parsec (e.g. le poste client est hors-ligne)
- HTTP 502: le client Parsec s'est vu refuser sa requête par le serveur Parsec (e.g. l'utilisateur Parsec a été révoqué)

`greeter_sas` est le code de 4 caractère à transmettre par un canal tiers au pair.

### `POST /invitations/<token>/claimer/3-wait-peer-trust`

Attend que le pair ait validé le code SAS qui lui a été fourni.

Request:

```python
{
}
```

Response:

```python
HTTP 200
{
}
```

ou

- HTTP 404 si le token est inconnu
- HTTP 409 si le pair a reset le processus (il faut repartir de la route `1-wait-peer-ready`)
- HTTP 503: le client Parsec n'a pas pu joindre le serveur Parsec (e.g. le poste client est hors-ligne)
- HTTP 502: le client Parsec s'est vu refuser sa requête par le serveur Parsec (e.g. l'utilisateur Parsec a été révoqué)

### `POST /invitations/<token>/claimer/4-finalize`

Ajoute le pair dans Parsec

Request:

```python
{
    "key": <base64>
}
```

Response:

```python
HTTP 200
{
}
```

ou

- HTTP 404 si le token est inconnu
- HTTP 409 si le pair a reset le processus (il faut repartir de la route `1-wait-peer-ready`)
- HTTP 503: le client Parsec n'a pas pu joindre le serveur Parsec (e.g. le poste client est hors-ligne)
- HTTP 502: le client Parsec s'est vu refuser sa requête par le serveur Parsec (e.g. l'utilisateur Parsec a été révoqué)

`key` est utilisé pour chiffrer le fichier de clé de Device résultant de l'opération d'enrôlement.

## Workspace

### `GET /workspaces`

Récupère la liste des workspaces.

Response:

```python
HTTP 200
{
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

`role` peut être: `OWNER`, `MANAGER`, `CONTRIBUTOR`, `READER`

### `POST /workspaces`

Créé un nouveau workspace.

Request:

```python
{
    "name": <string>
}
```

Response:

```python
HTTP 201
{
    "id": <uuid>
}
```

**Notes:**

- le nom d'un workspace n'a pas à être unique.
- la création d'un workspace peut se faire hors-ligne.

### `PATCH /workspaces/<id>`

Renomme un workspace.

Request:

```python
{
    "old_name": <string>,
    "new_name": <string>
}
```

Response:

```python
HTTP 200
{
}
```

ou

- HTTP 409: le workspace a déjà eu son nom changé
- HTTP 404: le workspace n'existe pas

**Notes:**

- le renommage d'un workspace n'impacte que l'utilisateur réalisant ce renommage (si le workspace est partagé avec d'autres utilisateurs, ceux-ci ne verront pas le changement de nom)

### `GET /workspace/<id>/share`

Récupère les informations de partage d'un workspace.

Response:

```python
HTTP 200
{
    "roles": {
        <email>: <role>
    }
}
```

ou

- HTTP 404: le workspace n'existe pas
- HTTP 503: le client Parsec n'a pas pu joindre le serveur Parsec (e.g. le poste client est hors-ligne)
- HTTP 502: le client Parsec s'est vu refuser sa requête par le serveur Parsec (e.g. l'utilisateur Parsec a été révoqué)

### `PATCH /workspace/<id>/share`

Partage un workspace.

Request:

```python
{
    "email": <string>,
    "role": <string ou null>
}
```

`role` peut être soit `null` (pour retirer le partage) soit une des strings: `OWNER`, `MANAGER`, `CONTRIBUTOR`, `READER`

Response:

```python
HTTP 200
{
}
```

ou

```python
HTTP 404
{
    "error": "unknown_workspace"
}
```

ou

```python
HTTP 404
{
    "error": "unknown_email"
}
```

ou

- HTTP 503: le client Parsec n'a pas pu joindre le serveur Parsec (e.g. le poste client est hors-ligne)

**Notes:**

- le renommage d'un workspace n'impacte que l'utilisateur réalisant ce renommage (si le workspace est partagé avec d'autres utilisateurs, ceux-ci ne verront pas le changement de nom)

## Dossiers

### `GET /workspace/<id>/folders`

Consulter l'arborescence d'un workspace.

Response:

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

ou

```python
HTTP 404
{
    "error": "unknown_workspace"
}
```

ou

- HTTP 503: le client Parsec n'a pas pu joindre le serveur Parsec (e.g. le poste client est hors-ligne et le chemin à accéder n'est pas dans le cache local)

### `POST /workspace/<id>/folders`

Créé un nouveau répertoire.

Request:

```python
{
    "name": <string>,
    "parent": <id>
}
```

Response:

```python
HTTP 201
{
    "id": <id>
}
```

ou

```python
HTTP 404
{
    "error": "unknown_workspace"
}
```

ou

```python
HTTP 404
{
    "error": "unknown_parent"
}
```

ou

- HTTP 503: le client Parsec n'a pas pu joindre le serveur Parsec (e.g. le poste client est hors-ligne et le chemin à accéder n'est pas dans le cache local)

### `POST /workspace/<id>/folders/rename`

Déplace/renomme un repertoire.

Request:

```python
{
    "id": <id>
    "new_name": <string>,
    "new_parent": <id or null>
}
```

Response:

```python
HTTP 200
{
}
```

ou

```python
HTTP 400
{
    "error": "destination_parent_not_a_folder"
}
```

ou

```python
HTTP 400
{
    "error": "source_not_a_folder"
}
```

ou

```python
HTTP 400
{
    "error": "cannot_move_root_folder"
}
```

ou

```python
HTTP 404
{
    "error": "unknown_workspace"
}
```

ou

```python
HTTP 404
{
    "error": "unknown_source_folder"
}
```

ou

```python
HTTP 404
{
    "error": "unknown_destination_parent_folder"
}
```

ou

- HTTP 403 si l'utilisateur n'a pas le profil `OWNER`/`MANAGER`/`CONTRIBUTER` sur le workspace
- HTTP 503: le client Parsec n'a pas pu joindre le serveur Parsec (e.g. le poste client est hors-ligne et le chemin à accéder n'est pas dans le cache local)

### `DELETE /workspace/<id>/folders/<id>`

Supprime un répertoire.

Request:

```python
{
}
```

Response:

```python
HTTP 204
{
}
```

ou

```python
HTTP 400
{
    "error": "cannot_delete_root_folder"
}
```

ou

```python
HTTP 403
{
    "error": "read_only_workspace"
}
```

ou

```python
HTTP 404
{
    "error": "not_a_folder"
}
```

ou

```python
HTTP 404
{
    "error": "unknown_workspace"
}
```

ou

```python
HTTP 404
{
    "error": "unknown_folder"
}
```

ou

- HTTP 503: le client Parsec n'a pas pu joindre le serveur Parsec (e.g. le poste client est hors-ligne et le chemin à accéder n'est pas dans le cache local)

## Fichiers

### `GET /workspace/<id>/files/<folder_id>`

Consulte l'arborescence des fichiers d'un workspace.

Response:

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
            "updated": <datetime>,
        },
        ...
    ]
}
```

ou

```python
HTTP 404
{
    "error": "unknown_workspace"
}
```

ou

```python
HTTP 404
{
    "error": "unknown_path"
}
```

ou

- HTTP 503: le client Parsec n'a pas pu joindre le serveur Parsec (e.g. le poste client est hors-ligne et le chemin à accéder n'est pas dans le cache local)

### `POST /workspace/<id>/files`

Créé un nouveau fichier.

Request:

En multipart pour les grands fichiers (> 1 Go)

```python
data={
    "parent": <id>
    }
files={
    "file": (
        "name": <string>,
        "content": <bytes>
    )
}
```

ou en base64 en json

```python
{
    "name": <string>,
    "parent": <id>,
    "content": <base64>
}
```

Response:

```python
HTTP 201
{
    "id": <id>
}
```

ou

```python
HTTP 404
{
    "error": "unknown_workspace"
}
```

ou

```python
HTTP 404
{
    "error": "unknown_path"
}
```

ou

- HTTP 503: le client Parsec n'a pas pu joindre le serveur Parsec (e.g. le poste client est hors-ligne et le chemin à accéder n'est pas dans le cache local)

### `POST /workspace/<id>/files/rename`

Déplace/renomme un fichier

Request:

```python
{
    "id": <id>
    "new_name": <string>,
    "new_folder": <id or null>
}
```

Response:

```python
HTTP 200
{
}
```

ou

```python
HTTP 400
{
    "error": "invalid_destination"
}
```

ou

```python
HTTP 404
{
    "error": "unknown_workspace"
}
```

ou

```python
HTTP 404
{
    "error": "unknown_path"
}
```

ou

- HTTP 503: le client Parsec n'a pas pu joindre le serveur Parsec (e.g. le poste client est hors-ligne et le chemin à accéder n'est pas dans le cache local)

### `DELETE /workspace/<id>/files/<id>`

Supprime un fichier.

Request:

```python
{
}
```

Response:

```python
HTTP 204
{
}
```

ou

```python
HTTP 404
{
    "error": "unknown_workspace"
}
```

ou

```python
HTTP 404
{
    "error": "unknown_file"
}
```

ou

- HTTP 503: le client Parsec n'a pas pu joindre le serveur Parsec (e.g. le poste client est hors-ligne et le chemin à accéder n'est pas dans le cache local)

### `POST /workspace/<id>/open/<id>`

Ouvre un fichier/répertoire.

Request:

```python
{
}
```

Response:

```python
HTTP 200
{
}
```

ou

```python
HTTP 404
{
    "error": "unknown_workspace"
}
```

ou

```python
HTTP 404
{
    "error": "unknown_file"
}
```

ou

- HTTP 503: le client Parsec n'a pas pu joindre le serveur Parsec (e.g. le poste client est hors-ligne)

### [NOT IMPLEMENTED] `GET /workspace/<id>/reencryption`

Récupère les information de rechiffrement du workspace.

Response:

```python
HTTP 200
{
    "need_reencryption": <boolean>,
    "user_revoked": [<string>, …],
    "role_revoked": [<string>, …],
    "reencryption_already_in_progress": <boolean>
}
```

ou

```python
HTTP 404
{
    "error": "unknown_workspace"
}
```

ou

```python
HTTP 404
{
    "error": "unknown_path"
}
```

ou

- HTTP 503: le client Parsec n'a pas pu joindre le serveur Parsec (e.g. le poste client est hors-ligne)

`user_revoked` liste des email des HumanHandle dont le user a été révoqué
`role_revoked` liste des email des HumanHandle dont le user a perdu l'accès au workspace
`reencryption_already_in_progress` le rechiffrement est déjà en cours

### [NOT IMPLEMENTED] `POST /workspace/<id>/reencryption`

Lance le rechiffrement du workspace.

Request:

```python
{
}
```

Response:

```python
HTTP 200
{
}
```

ou

```python
HTTP 404
{
    "error": "unknown_workspace"
}
```

ou

- HTTP 403 si l'utilisateur n'a pas le profil `OWNER` sur le workspace
ou

- HTTP 503: le client Parsec n'a pas pu joindre le serveur Parsec (e.g. le poste client est hors-ligne)

## Récupération d'appareil

### `POST /recovery/export`

Créé un fichier de récupération pour le device authentifié.
Ce fichier de récupération sert à créer de nouveaux devices pour l'utilisateur, cela permet
notamment de récupérer son compte en cas de perte de son ordinateur ou bien d'oubli
de mot de passe.

Request:

```python
{
}
```

Response:

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

Request:

```python
{
    "recovery_device_file_content": <base64>
    "recovery_device_passphrase": <string>
    "new_device_key": <string>
}
```

Response:

```python
HTTP 200
{
}
```

ou

```python
HTTP 400
{
    "error": "invalid_passphrase"
}
```
