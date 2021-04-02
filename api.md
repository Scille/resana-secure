TODO:
- keep-alive request
- sync system
- reencryption system (get reencryption needs, start&resume reencryption)


Pre-Authentification
====================


`GET <server-resana>/resana-secure/master-key`
----------------------------------------------

Récupère la "encrypted master key RESANA Secure" depuis le serveur RESANA.

Response:
```
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


`POST <server-resana>/auth/password`
------------------------------------

Changement du mot de passe RESANA ainsi que de la master key RESANA Secure.

Request:
```
{
    "old_password": <string>,
    "new_password": <string>,
    "new_resana_secure_master_key": <base64>
}
```

Response:
```
HTTP 200
{
}
```
ou
- HTTP 409: le mot de passe a déjà été changé (i.e. `old_password` n'est pas le mot de passe actuel)


Authentification
================


`POST /auth`
------------

Procède à l'authentification auprès du client Parsec.
Cette requête doit être réalisée en tout premier, elle fournit un cookie
de session permettant d'authentifier les autres requêtes.

Request:
```
{
    "email": <string>,
    "key": <base64>
}
```
`email` correspondant à l'email utilisé lors de l'enrôlement RESANA Secure.

Response:
```
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
```
Authorization: Bearer <token>
```


`DELETE /auth`
--------------

Met fin à l'authentification auprès du client Parsec et invalide the token d'authentification.

Response:
```
HTTP 200
Set-Cookie: session=; Expires=Thu, 01-Jan-1970 00:00:00 GMT; Max-Age=0; Path=/
{
}
```


`DELETE /auth`
--------------

Met fin à l'authentification auprès du client Parsec et invalide the token d'authentification.

Response:
```
HTTP 200
Set-Cookie: session=; Expires=Thu, 01-Jan-1970 00:00:00 GMT; Max-Age=0; Path=/
{
}
```


Utilisateurs & invitations
==========================

/**************
`GET /humans?q=<query>&page=<int>&per_page=<int>&omit_revoked=<bool>`
------------

`query` est recherchée contre les champs human_handle.email et human_handle.label, les match partiel sont acceptés.
(par example, `query=john` va matcher contre `email:john.doe@example.com` et contre `Bob Johnson`)

Response:
```
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
- HTTP 502: le client Parsec s'est vu refusé sa requête par le serveur Parsec (e.g. l'utilisateur Parsec a été révoqué)

`profile` peut être: `ADMIN` ou `STANDARD`
**************/

`POST /humans/<email>/revoke`
-----------------------------

Request:
```
{
}
```

Response:
```
HTTP 200
{
}
```
ou
- HTTP 404 si email inconnu
- HTTP 403 si l'utilisateur actuel n'a pas le profil administrateur sur l'organisation Parsec
- HTTP 503: le client Parsec n'a pas pu joindre le serveur Parsec (e.g. le poste client est hors-ligne)
- HTTP 502: le client Parsec s'est vu refusé sa requête par le serveur Parsec (e.g. l'utilisateur Parsec a été révoqué)


`GET /invitations`
------------------

Récupère la list des invitations en cours.

Response:
```
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
- HTTP 502: le client Parsec s'est vu refusé sa requête par le serveur Parsec (e.g. l'utilisateur Parsec a été révoqué)

`status` peut être: `IDLE` ou `READY`
Notes:
- Le statut `READY` indique que la personne invitée s'est connectée au serveur Parsec
avec pour intention de procéder à l'enrôlement.
- Il ne peut y avoir que zéro ou une seule invitation de device à la fois.



`POST /invitations`
-------------------

Créer une nouvelle invitation.

Request:
```
{
    "type": "user",
    "claimer_email": <string>
}

```
ou pour un device
```
{
    "type": "device"
}

```

Response:
```
HTTP 200
{
    "token": <uuid>
}
```
ou
```
HTTP 400
{
    "error":  "claimer_already_member"
}
```
ou
- HTTP 403 si l'utilisateur actuel n'a pas le profil administrateur sur l'organisation Parsec et tente d'inviter un autre utilisateur.
- HTTP 503: le client Parsec n'a pas pu joindre le serveur Parsec (e.g. le poste client est hors-ligne)
- HTTP 502: le client Parsec s'est vu refusé sa requête par le serveur Parsec (e.g. l'utilisateur Parsec a été révoqué)

La création d'invitation est idempotent (si une invitation existe déjà, elle ne sera pas recréée et le token existant sera retourné).


`DELETE /invitations/<token>`
-------------------------

Supprime une invitation.

Request:
```
{
    "token": <uuid>
}

```

Response:
```
HTTP 204
{
}
```
ou
```
HTTP 400
{
    "error": "invitation_already_used"
}
```
ou
- HTTP 404 si le token n'existe pas
- HTTP 503: le client Parsec n'a pas pu joindre le serveur Parsec (e.g. le poste client est hors-ligne)
- HTTP 502: le client Parsec s'est vu refusé sa requête par le serveur Parsec (e.g. l'utilisateur Parsec a été révoqué)


Enrôlement (greeter)
====================

`POST /invitations/<token>/greeter/1-wait-peer-ready`
-------------------------------------------------------

Démarre la phase d'enrôlement et attend que le pair à enrôler ait rejoins le serveur Parsec.

Request:
```
{
}
```

Response:
```
HTTP 200
{
    "type": <string>,
    "greeter_sas": <string>
}
```
ou
```
HTTP 400
{
    "error": "invitation_already_used"
}
```
ou
- HTTP 403 si l'utilisateur n'a pas le profil `ADMIN` et tente d'inviter un nouvel utilisateur
- HTTP 404 si le token est inconnu
- HTTP 503: le client Parsec n'a pas pu joindre le serveur Parsec (e.g. le poste client est hors-ligne)
- HTTP 502: le client Parsec s'est vu refusé sa requête par le serveur Parsec (e.g. l'utilisateur Parsec a été révoqué)

`type` est `DEVICE` ou `USER`
`greeter_sas` est le code de 4 caractère à transmettre par un canal tiers au pair.


`POST /invitations/<token>/greeter/2-wait-peer-trust`
--------------------------------------------

Attend que le pair ait validé le code SAS qui lui a été fourni.

Request:
```
{
}
```

Response:
```
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
- HTTP 502: le client Parsec s'est vu refusé sa requête par le serveur Parsec (e.g. l'utilisateur Parsec a été révoqué)

`candidate_claimer_sas` est une liste de quatre codes dont un seul correspond
au code SAS du pair. L'utilisateur est donc obligé de se concerter avec le pair
pour déterminer lequel est le bon.


`POST /invitations/<token>/greeter/3-check-trust`
-------------------------------------------------

Vérifie le code SAS fourni par le pair.

Request:
```
{
    "claimer_sas": <string>
}
```

Response:
```
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
- HTTP 502: le client Parsec s'est vu refusé sa requête par le serveur Parsec (e.g. l'utilisateur Parsec a été révoqué)


`POST /invitations/<token>/greeter/4-finalize`
----------------------------------------------

Ajoute le pair dans Parsec

Request:
pour un enrôlement de device:
```
{
}
```
ou pour un enrôlement de user:
```
{
    "claimer_email": <string>,
    "granted_profile": <string>
}
```
`granted_profile` peut être: `ADMIN` ou `STANDARD`
(seuls les profiles `ADMIN` peuvent à leur tour inviter de nouveaux utilisateurs)

Response:
```
HTTP 200
{
}
```
ou
- HTTP 403 si l'utilisateur n'a pas le profil `ADMIN` et tente d'inviter un nouvel utilisateur
- HTTP 404 si le token est inconnu
- HTTP 409 si le pair a reset le processus (il faut repartir de la route `1-wait-peer-ready`)
- HTTP 503: le client Parsec n'a pas pu joindre le serveur Parsec (e.g. le poste client est hors-ligne)
- HTTP 502: le client Parsec s'est vu refusé sa requête par le serveur Parsec (e.g. l'utilisateur Parsec a été révoqué)


Enrôlement (claimer)
====================


`POST /invitations/<token>/claimer/0-retreive-info`
-------------------------------------------------------

Démarre la phase d'enrôlement et récupères des informations de base sur l'invitation.

Request:
```
{
    "token": <uuid>
}
```

Response:
```
HTTP 200
{
    "type": <string>,
    "greeter_email": <string>,
}
```
ou
- HTTP 404 si le token est inconnu
- HTTP 503: le client Parsec n'a pas pu joindre le serveur Parsec (e.g. le poste client est hors-ligne)
- HTTP 502: le client Parsec s'est vu refusé sa requête par le serveur Parsec (e.g. l'utilisateur Parsec a été révoqué)

`type` est `DEVICE` ou `USER`
`candidate_greeter_sas` est une liste de quatre codes dont un seul correspond
au code SAS du pair. L'utilisateur est donc obligé de se concerter avec le pair
pour déterminer lequel est le bon.


`POST /invitations/<token>/claimer/1-wait-peer-ready`
-------------------------------------------------------

Attend que le pair qui enrôle ait rejoins le serveur Parsec.

Request:
```
{
    "token": <uuid>
}
```

Response:
```
HTTP 200
{
    "candidate_greeter_sas": [<string>, …]
}
```
ou
- HTTP 404 si le token est inconnu
- HTTP 503: le client Parsec n'a pas pu joindre le serveur Parsec (e.g. le poste client est hors-ligne)
- HTTP 502: le client Parsec s'est vu refusé sa requête par le serveur Parsec (e.g. l'utilisateur Parsec a été révoqué)

`type` est `DEVICE` ou `USER`
`candidate_greeter_sas` est une liste de quatre codes dont un seul correspond
au code SAS du pair. L'utilisateur est donc obligé de se concerter avec le pair
pour déterminer lequel est le bon.



`POST /invitations/<token>/claimer/2-check-trust`
-------------------------------------------------

Vérifie le code SAS fourni par le pair.

Request:
```
{
    "greeter_sas": <string>
}
```

Response:
```
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
- HTTP 502: le client Parsec s'est vu refusé sa requête par le serveur Parsec (e.g. l'utilisateur Parsec a été révoqué)

`greeter_sas` est le code de 4 caractère à transmettre par un canal tiers au pair.


`POST /invitations/<token>/claimer/3-wait-peer-trust`
-----------------------------------------------------

Attend que le pair ait validé le code SAS qui lui a été fourni.

Request:
```
{
}
```

Response:
```
HTTP 200
{
}
```
ou
- HTTP 404 si le token est inconnu
- HTTP 409 si le pair a reset le processus (il faut repartir de la route `1-wait-peer-ready`)
- HTTP 503: le client Parsec n'a pas pu joindre le serveur Parsec (e.g. le poste client est hors-ligne)
- HTTP 502: le client Parsec s'est vu refusé sa requête par le serveur Parsec (e.g. l'utilisateur Parsec a été révoqué)


`POST /invitations/<token>/claimer/4-finalize`
----------------------------------------------

Ajoute le pair dans Parsec

Request:
```
{
    "key": <base64>
}
```

Response:
```
HTTP 200
{
}
```
ou
- HTTP 404 si le token est inconnu
- HTTP 409 si le pair a reset le processus (il faut repartir de la route `1-wait-peer-ready`)
- HTTP 503: le client Parsec n'a pas pu joindre le serveur Parsec (e.g. le poste client est hors-ligne)
- HTTP 502: le client Parsec s'est vu refusé sa requête par le serveur Parsec (e.g. l'utilisateur Parsec a été révoqué)

`key` est utilisé pour chiffrer le fichier de clé de Device résultant de l'opération d'enrôlement.


Workspace
=========


`GET /workspaces`
-----------------

Récupère la list des workspaces.

Response:
```
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


`POST /workspaces`
-----------------

Créé un nouveau workspace.

Request:
```
{
    "name": <string>
}
```

Response:
```
HTTP 201
{
    "id": <uuid>
}
```
Note: le nom d'un workspace n'a pas à être unique.
Note2: la création d'un workspace peut se faire hors-ligne.


`PATCH /workspaces/<id>`
------------------------

Renomme un workspace.

Request:
```
{
    "old_name": <string>,
    "new_name": <string>
}
```

Response:
```
HTTP 200
{
}
```
ou
- HTTP 409: le workspace a déjà eu son nom changé
- HTTP 404: le workspace n'existe pas

Note: le renommage d'un workspace n'impacte que l'utilisateur réalisant ce renommage (si le workspace est partagé avec d'autres utilisateurs, ceux-ci ne verront pas le changement de nom)


`GET /workspace/<id>/share`
----------------------------

Récupère le informations de partage d'un workspace.

Response:
```
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
- HTTP 502: le client Parsec s'est vu refusé sa requête par le serveur Parsec (e.g. l'utilisateur Parsec a été révoqué)


`PATCH /workspace/<id>/share`
-----------------------------

Partager un workspace.

Request:
```
{
    "email": <string>,
    "role": <string ou null>
}
```
`role` peut être soit `null` (pour retirer le partage) soit une des strings: `OWNER`, `MANAGER`, `CONTRIBUTOR`, `READER`

Response:
```
HTTP 200
{
}
```
ou
```
HTTP 404
{
    "error": "unknown_workspace"
}
```
ou
```
HTTP 404
{
    "error": "unknown_email"
}
```
ou
- HTTP 503: le client Parsec n'a pas pu joindre le serveur Parsec (e.g. le poste client est hors-ligne)

Note: le renommage d'un workspace n'impacte que l'utilisateur réalisant ce renommage (si le workspace est partagé avec d'autres utilisateurs, ceux-ci ne verront pas le changement de nom)


Dossiers
========

`GET /workspace/<id>/folders`
----------------------------------

Consulter l'arborescence d'un workspace.

Response:
```
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
```
HTTP 404
{
    "error": "unknown_workspace"
}
```
ou
- HTTP 503: le client Parsec n'a pas pu joindre le serveur Parsec (e.g. le poste client est hors-ligne et le chemin à accèder n'est pas dans le cache local)


`POST /workspace/<id>/folders`
------------------------------

Créer un nouveau répertoire.

Request:
```
{
    "name": <string>,
    "parent": <id>
}
```

Response:
```
HTTP 201
{
    "id": <id>
}
```
ou
```
HTTP 404
{
    "error": "unknown_workspace"
}
```
ou
```
HTTP 404
{
    "error": "unknown_parent"
}
```
ou
- HTTP 503: le client Parsec n'a pas pu joindre le serveur Parsec (e.g. le poste client est hors-ligne et le chemin à accèder n'est pas dans le cache local)


`POST /workspace/<id>/folders/rename`
-----------------------------

Déplacer/renommer un repertoire.

Request:
```
{
    "id": <id>
    "new_name": <string>,
    "new_parent": <id or null>
}
```

Response:
```
HTTP 200
{
}
```
ou
```
HTTP 400
{
    "error": "destination_parent_not_a_folder"
}
```
ou
```
HTTP 400
{
    "error": "source_not_a_folder"
}
```
ou
```
HTTP 400
{
    "error": "cannot_move_root_folder"
}
```
ou
```
HTTP 404
{
    "error": "unknown_workspace"
}
```
ou
```
HTTP 404
{
    "error": "unknown_source_folder"
}
```
ou
```
HTTP 404
{
    "error": "unknown_destination_parent_folder"
}
```
ou
- HTTP 403 si l'utilisateur n'a pas le profil `OWNER`/`MANAGER`/`CONTRIBUTER` sur le workspace
- HTTP 503: le client Parsec n'a pas pu joindre le serveur Parsec (e.g. le poste client est hors-ligne et le chemin à accèder n'est pas dans le cache local)


`DELETE /workspace/<id>/folders/<id>`
-----------------------------------

Supprimer un répertoire.

Request:
```
{
}
```

Response:
```
HTTP 204
{
}
```
ou
```
HTTP 400
{
    "error": "cannot_delete_root_folder"
}
```
ou
```
HTTP 403
{
    "error": "read_only_workspace"
}
```
ou
```
HTTP 404
{
    "error": "not_a_folder"
}
```
ou
```
HTTP 404
{
    "error": "unknown_workspace"
}
```
ou
```
HTTP 404
{
    "error": "unknown_folder"
}
```
ou
- HTTP 503: le client Parsec n'a pas pu joindre le serveur Parsec (e.g. le poste client est hors-ligne et le chemin à accèder n'est pas dans le cache local)


Fichiers
========


`GET /workspace/<id>/files/<folder_id>`
----------------------------------

Consulter l'arborescence des fichiers d'un workspace.

Response:
```
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
```
HTTP 404
{
    "error": "unknown_workspace"
}
```
ou
```
HTTP 404
{
    "error": "unknown_path"
}
```
ou
- HTTP 503: le client Parsec n'a pas pu joindre le serveur Parsec (e.g. le poste client est hors-ligne et le chemin à accèder n'est pas dans le cache local)


`POST /workspace/<id>/files`
----------------------------

Créer un nouveau fichier.

Request:
```
{
    "name": <string>,
    "parent": <id>,
    "content": <base64>
}
```

Response:
```
HTTP 201
{
    "id": <id>
}
```
ou
```
HTTP 404
{
    "error": "unknown_workspace"
}
```
ou
```
HTTP 404
{
    "error": "unknown_path"
}
```
ou
- HTTP 503: le client Parsec n'a pas pu joindre le serveur Parsec (e.g. le poste client est hors-ligne et le chemin à accèder n'est pas dans le cache local)


`POST /workspace/<id>/files/rename`
-----------------------------

Déplacer/renommer un fichier

Request:
```
{
    "id": <id>
    "new_name": <string>,
    "new_folder": <id or null>
}
```

Response:
```
HTTP 200
{
}
```
ou
```
HTTP 400
{
    "error": "invalid_destination"
}
```
ou
```
HTTP 404
{
    "error": "unknown_workspace"
}
```
ou
```
HTTP 404
{
    "error": "unknown_path"
}
```
ou
- HTTP 503: le client Parsec n'a pas pu joindre le serveur Parsec (e.g. le poste client est hors-ligne et le chemin à accèder n'est pas dans le cache local)


`DELETE /workspace/<id>/files/<id>`
-----------------------------------

Supprimer un fichier.

Request:
```
{
}
```

Response:
```
HTTP 204
{
}
```
ou
```
HTTP 404
{
    "error": "unknown_workspace"
}
```
ou
```
HTTP 404
{
    "error": "unknown_file"
}
```
ou
- HTTP 503: le client Parsec n'a pas pu joindre le serveur Parsec (e.g. le poste client est hors-ligne et le chemin à accèder n'est pas dans le cache local)


`POST /workspace/<id>/open/<id>`
--------------------------------

Ouvrir un fichier/répertoire.

Request:
```
{
}
```

Response:
```
HTTP 200
{
}
```
ou
```
HTTP 404
{
    "error": "unknown_workspace"
}
```
ou
```
HTTP 404
{
    "error": "unknown_file"
}
```
ou
- HTTP 503: le client Parsec n'a pas pu joindre le serveur Parsec (e.g. le poste client est hors-ligne)


/**************
`GET /workspace/<id>/reencryption`
----------------------------------

Récupère les information de rechiffrement du workspace.

Response:
```
HTTP 200
{
    "need_reencryption": <boolean>,
    "user_revoked": [<string>, …],
    "role_revoked": [<string>, …],
    "reencryption_already_in_progress": <boolean>
}
```
ou
```
HTTP 404
{
    "error": "unknown_workspace"
}
```
ou
```
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


`POST /workspace/<id>/reencryption`
----------------------------------------

Lance le rechiffrement du workspace.

Request:
```
{
}
```

Response:
```
HTTP 200
{
}
```
ou
```
HTTP 404
{
    "error": "unknown_workspace"
}
```
ou
- HTTP 403 si l'utilisateur n'a pas le profil `OWNER` sur le workspace
ou
- HTTP 503: le client Parsec n'a pas pu joindre le serveur Parsec (e.g. le poste client est hors-ligne)
**************/