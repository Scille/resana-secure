{
# Some OS (Centos7) don't load the user's path properly for the ip command
export PATH="$PATH:/usr/sbin"

# Machine type detection: whether we're inside a container, a virtual machine, bare-metal, etc.
machine_type= # unknown
[ -n "$IMAGE_NAME" ] && machine_type=docker
echo "MACHINE_TYPE:$machine_type"

echo "ARCH:$(uname -m)"

# System
if [ "$machine_type" = docker ]; then
  echo "HOSTNAME:$IMAGE_NAME"
  echo "IMAGE_ID:$IMAGE_ID"
  echo "META:IMAGE_ID|$IMAGE_ID"
  echo "META:IMAGE_CREATION_DATE|$IMAGE_CREATION_DATE"

  env | grep CBW_LABEL | while read -r label;
  do
    echo "${label//CBW_LABEL[0-9]*=/META:}"
  done
else
  if command -v hostname > /dev/null ; then
    echo "HOSTNAME:$(hostname)"
  elif [ -f /etc/hostname ]; then
    echo "HOSTNAME:$(head -n 1 /etc/hostname)"
  fi
  echo "KERNEL_VERSION:$(uname -r)"
  echo "META:kernel-version|$(uname -r)"
fi

# OS identification
# Rely on /etc/os-release, which should be present on all the modern distributions.
# Use VERSION_ID to get a locale-agnostic version number. See os-release(5).

awk -F= -f - /etc/os-release <<'EOF'
  {
    key = $1
    value = $2
    # Remove enclosing quotes in value.
    sub(/^"/, "", value)
    sub(/"$/, "", value)
    variables[key] = value
  }
  END {
    print "OS_NAME:" variables["NAME"]
    print "OS_VERSION:" variables["VERSION_ID"]
  }
EOF

# Legacy OS identification
# Compute a pretty name based on all kinds of sources.

OS_PRETTYNAME=$(awk '/PRETTY_NAME/' /etc/*-release | sed 's/PRETTY_NAME=//' | sed 's/\"//g')
if [ -z "${OS_PRETTYNAME}" ]; then
  [ -e "/etc/redhat-release" ] && OS_PRETTYNAME="$(head -n 1 "/etc/redhat-release")"
  [ -e "/etc/SuSE-release" ] && OS_PRETTYNAME="$(head -n 1 "/etc/SuSE-release")"
  [ -n "$(lsb_release -ds 2>/dev/null)" ] && OS_PRETTYNAME=$(lsb_release -ds | tr '"' ' ')
  [ -e "/etc/debian_version" ] && OS_PRETTYNAME="Debian $(cat /etc/debian_version)"
  [ -e "/etc/manjaro-release" ] && OS_PRETTYNAME="$(head -n 1 "/etc/manjaro-release")"
  [ -z "$OS_PRETTYNAME" ] && OS_PRETTYNAME="Not Found"
fi

if [ "$OS_PRETTYNAME" = "Red Hat Enterprise Linux" ]; then
  [ -e "/etc/system-release-cpe" ] && OS_PRETTYNAME="$OS_PRETTYNAME $(awk -F: '{print $5}' /etc/system-release-cpe)"
fi

if [ "$OS_PRETTYNAME" = "VMware Photon OS/Linux" ]; then
  [ -e "/etc/photon-release" ] && OS_PRETTYNAME="$(head -n 1 "/etc/photon-release")"
fi

echo "OS_PRETTYNAME:${OS_PRETTYNAME}"

# Boot time, and whether a reboot is required or not.
if [ "$machine_type" != docker ]; then
  REBOOT=false; [ -f '/var/run/reboot-required' ] && REBOOT=true

  # When it exists, check the exit code of needs-restarting
  if command -v needs-restarting > /dev/null ; then
    needs-restarting -r > /dev/null 2>&1
    # CentOS 6 does not support -r and returns 2 in that case, so we accept $? = 1 and nothing else.
    [ "$?" -eq 1 ] && REBOOT=true
  fi

  echo "REBOOT:${REBOOT}"

  boot_time=$(uptime -s 2> /dev/null) && echo "BOOT_TIME:$(date -d "$boot_time" +%FT%T%z)"
fi

# List all the IPv4 addresses
ip address | sed -ne 's/^\s*inet \([0-9.]\+\).*$/IP:\1/p'

# Packages
if command -v dpkg-query > /dev/null ; then
  dpkg-query -W -f='PACKAGE:${Package}|${Version}|${Status}\n' | sed -n -E 's/\|(hold|install) ok installed$//p'
elif command -v rpm > /dev/null ; then
  rpm -qa --qf='PACKAGE:%{NAME}.%{ARCH}|%{VERSION}-%{RELEASE}\n'
elif command -v pacman > /dev/null ; then
  pacman -Q | awk '{print "PACKAGE:"$1"|"$2}'
elif command -v tdnf > /dev/null ; then
  tdnf list installed | awk '{print "PACKAGE:"$1"|"$2}'
elif command -v apk > /dev/null ; then
  apk info -v | sed 's/^\(.*\)-\([^-]*\)-\([^-]*\)$/PACKAGE:\1|\2-\3/; t; s/^/ERROR: Cannot interpret line: /'
else
  echo 'ANOMALY:No package manager.'
fi | sed -ne 'p;s/^PACKAGE:omi\(.x86_64\)\?|/LINUX_APPLICATION:omi|/p'

# Services
if command -v systemctl > /dev/null; then
  systemctl list-unit-files --no-legend -t service | awk '{ sub(/\.service$/, "", $1); print "SERVICE:" $1 "|" $2 }'
fi

# Applicative packages managers.

if command -v pip > /dev/null; then
  # six==1.14.0 → PIP:six|1.14.0
  pip freeze | awk -F == '{ print "PIP:" $1 "|" $2 }'
fi

if command -v gem > /dev/null; then
  # racc (1.5.2, default: 1.5.1)
  gem list --quiet | awk '
    {
      name = $1
      vstring = $0
      sub(/^[^(]*\(/, "", vstring)
      sub(/\)$/, "", vstring)
      gsub(/default: /, "", vstring)
      split(vstring, versions, ", ")
      for (i in versions) {
        print "GEM:" name "|" versions[i]
      }
    }
  '
fi

# Third-party software detection.
if [ -n "$ORACLE_HOME" ]; then
  echo '# ORACLE_HOME is set. Performing Oracle database detection...'
  "$ORACLE_HOME/OPatch/opatch" lsinventory | awk -F'[ \t]{2,}' '
    # Oracle Database 19c           19.0.0.0.0
    /^Oracle Database / {
      product = $1
      version = $2
    }

    # Patch description:  "Database Release Update : 19.9.0.0.201020 (31771877)"
    $1 == "Patch description:" {
      if (match($2, /"Database Release Update : (\S+)/, a)) {
        version = a[1]
      }
    }

    END {
      if (product) {
        # LINUX_APPLICATION:Oracle Database 19c|19.9.0.0.201020
        print "LINUX_APPLICATION:" product "|" version
      } else {
        print "# No Oracle database found."
      }
    }
  '
fi

if command -v docker > /dev/null ; then
  # Docker version 20.10.8, build 3967b7d → NVD_APPLICATION:cpe:/a:docker:docker:20.10.8
  docker --version | sed -ne 's/^Docker version \([^ ,]\+\).*$/NVD_APPLICATION:cpe:\/a:docker:docker:\1/p'
fi

if command -v redis-server > /dev/null ; then
  # Redis server v=6.2.6 sha=00000000:0 malloc=jemalloc-5.1.0 bits=64 build=fdd28bd28db05332
  redis-server --version | sed -ne 's/^Redis server v=\([^ ]\+\).*$/NVD_APPLICATION:redis|\1/p'
fi

if command -v node > /dev/null ; then
  # v16.14.2
  node --version | sed -ne 's/^v\([^ ]\+\)$/NVD_APPLICATION:cpe:\/a:nodejs:node.js:\1/p'
fi

if command -v yarn > /dev/null ; then
  # 1.22.18
  yarn --version | sed -ne 's/^\([^ ]\+\)$/NVD_APPLICATION:cpe:\/a:yarnpkg:yarn:\1/p'
fi

if command -v npm > /dev/null ; then
  # 8.5.0
  npm --version | sed -ne 's/^\([^ ]\+\)$/NVD_APPLICATION:cpe:\/a:npmjs:npm:\1/p'
fi

if command -v php > /dev/null ; then
  # 8.1.13
  php -v | sed -n 's/PHP \([0-9]\+\.[0-9]\+\.[0-9]\+\).*/APPLICATION:php|\1/p'
fi

if command -v mariadbd > /dev/null ; then
  # mariadbd  Ver 10.7.3-MariaDB-1:10.7.3+maria~focal for debian-linux-gnu on x86_64 (mariadb.org binary distribution)
  mariadbd --version | sed -ne 's/^\S\+ \+Ver \([0-9.]\+\).*$/NVD_APPLICATION:mariadb|\1/p'
fi

if command -v mysqld > /dev/null ; then
  # /usr/sbin/mysqld  Ver 8.0.24 for Linux on x86_64 (MySQL Community Server - GPL)
  mysqld --version | sed -ne 's/^\S\+ \+Ver \([0-9.]\+\).*MySQL.*$/NVD_APPLICATION:mysql|\1/p'
  # Veiller à exclure mariadb, qui répond ainsi :
  # mysqld  Ver 10.7.3-MariaDB-1:10.7.3+maria~focal for debian-linux-gnu on x86_64 (mariadb.org binary distribution)
fi

if command -v postgres > /dev/null ; then
  # postgres(PostgreSQL) 12.13 (Ubuntu 12.13-0ubuntu0.20.04.1)
  postgres -V | sed -n 's/^postgres (PostgreSQL) \([0-9]\+\.[0-9]\+\).*$/NVD_APPLICATION:cpe:\/a:postgresql:postgresql:\1/p'
elif command -v psql > /dev/null ; then
  # psql (PostgreSQL) 12.13 (Ubuntu 12.13-0ubuntu0.20.04.1)
  psql -V | sed -n 's/^psql (PostgreSQL) \([0-9]\+\.[0-9]\+\).*$/NVD_APPLICATION:cpe:\/a:postgresql:postgresql:\1/p'
fi

if command -v java > /dev/null ; then
  # Pour Eclipse Temurin, `java -version` affiche :
  #
  #   openjdk version "18.0.2" 2022-07-19
  #   OpenJDK Runtime Environment Temurin-18.0.2+9 (build 18.0.2+9)
  #   OpenJDK 64-Bit Server VM Temurin-18.0.2+9 (build 18.0.2+9, mixed mode, sharing)
  #
  # La notation « Nom (build N) » est commune à toutes les distributions de Java. Servons-nous en pour extraire la
  # version de Java, et pour éliminer les lignes qui ne nous intéressent pas. Chaque ligne donnant un build génèrera une
  # APPLICATION. On s’attend à avoir une application pour le JRE, puis une pour la JVM.
  #
  # Ajout d'une exception sur la notation « Nom (build N) » pour le cas ci-dessous
  #   OpenJDK Runtime Environment (IcedTea 2.6.22) (7u261-2.6.22-1~deb8u1) OpenJDK 64-Bit Server VM (build 24.261-b02, mixed mode)
  java -version 2>&1 | grep 'OpenJDK Runtime Environment' | sed -r 's/.*\(([678]u[0-9]+[^)]*).*|.*build ([^,)) ]+).*/LINUX_APPLICATION:\0|\1\2/'
fi

# Détection ELK
# -------------
#
# On détectait historiquement les versions ELK en lançant des --version, qui est une convention qui marche assez bien.
# Il s’avère cependant que pour la suite ELK, lancer --version demande des droits root et peut faire planter des
# instances ELK en production. Optons donc pour une approche plus passive en explorant le système de fichier.
#
# Deux modes d’installation sont supportés :
#  - l’installation par paquet DEB/RPM,
#  - Docker.
#
# Dans les deux cas, l’installation se trouvera sous /usr/share/. On pourrait mieux gérer les installations moins
# orthodoxes en cherchant le chemin absolu de la commande elasticsearch par exemple, mais il s’avère que les exécutables
# ELK ne sont pas mis dans les PATH par défaut, étant donné qu’ils sont destinés à être lancés par systemd.

# Exemple : /usr/share/elasticsearch/lib/elasticsearch-7.16.1.jar
if [ -d /usr/share/elasticsearch/lib/ ]; then
  find /usr/share/elasticsearch/lib/ -printf '%f\n' | sed -ne 's/^elasticsearch-\([0-9][0-9.]*\)\.jar$/NVD_APPLICATION:cpe:\/a:elastic:elasticsearch:\1/p'
fi

if [ -f /usr/share/kibana/package.json ]; then
  sed -ne 's/^  "version": "\([^"]*\)",\?$/NVD_APPLICATION:cpe:\/a:elastic:kibana:\1/p' /usr/share/kibana/package.json
fi

# Exemple de fragment du Gemfile.lock qui nous intéresse :
#
# ```
# PATH
#   remote: logstash-core
#   specs:
#     logstash-core (7.16.1-java)
# ```
#
if [ -f /usr/share/logstash/Gemfile.lock ]; then
  sed -ne 's/^    logstash-core (\([0-9][0-9.]*\).*$/NVD_APPLICATION:cpe:\/a:elastic:logstash:\1/p' /usr/share/logstash/Gemfile.lock
fi

# filebeat est écrit en Go et n’a aucun de fichier de métadonnées. Comme il semble avoir une sous-commande version
# plutôt efficace, on peut se permettre de l’appeler sans trop d’impacts, contrairement aux autres programmes ELK.
# Le chemin de l’exécutable a changé entre la version 6 et 7, donc ajoutons les deux candidats dans le PATH.
if filebeat=$(PATH="$PATH:/usr/share/filebeat:/usr/share/filebeat/bin" command -v filebeat) ; then
  # filebeat version 7.14.1 (amd64), libbeat 7.14.1 [703d589a09cfdbfd7f84c1d990b50b6b7f62ac29 built 2021-08-26 09:12:57 +0000 UTC]
  "$filebeat" version | sed -ne 's/^filebeat version \([^ ,]\+\).*$/NVD_APPLICATION:cpe:\/a:elastic:filebeat:\1/p'
fi

if [ -f /opt/gitlab/version-manifest.txt ]; then
  # gitlab-ce     14.3.0
  awk '
    $1 == "gitlab-ce" { print "NVD_APPLICATION:cpe:2.3:a:gitlab:gitlab:" $2 ":-:-:-:community:-:-:-" }
    $1 == "gitlab-ee" { print "NVD_APPLICATION:cpe:2.3:a:gitlab:gitlab:" $2 ":-:-:-:enterprise:-:-:-" }
  ' /opt/gitlab/version-manifest.txt
fi

}
