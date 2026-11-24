# Mission Quota

[Français](#français) · [English](#english)

## Français

### Connecter ChatGPT

Démarre Mission Quota et ouvre son interface Web. Clique sur **Connecter mon compte ChatGPT** puis **Ouvrir OpenAI**. Connecte-toi sur la page OpenAI et saisis le code temporaire du panneau. Tu saisis ton mot de passe uniquement sur le site d’OpenAI. Si la connexion par appareil est bloquée, vérifie le réglage dans les paramètres de sécurité de ChatGPT ou auprès de l’administrateur de ton espace.

Reviens au panneau et clique sur **Tester la lecture**. Les fenêtres et leurs heures de recharge apparaissent dès qu’OpenAI renvoie un relevé.

### Activer MQTT et le LilyGO

1. Vérifie que **Mosquitto broker** et l’intégration MQTT sont actifs dans Home Assistant. Pour utiliser le courtier détecté par Home Assistant, laisse `mqtt_host` vide. Pour un autre courtier, renseigne son adresse, son port et ses identifiants.
2. Si un collecteur publie déjà sur les mêmes topics, arrête-le et désactive sa relance automatique.
3. Dans **Configuration**, active `publish_enabled`, enregistre puis redémarre l’application. Le panneau doit afficher **Connecté** pour MQTT.
4. Dans **Paramètres → Appareils et services → MQTT**, ouvre l’appareil **Mission Quota**. Les quatre capteurs indiquent les pourcentages et heures de recharge des deux fenêtres. Tu peux les ajouter à un tableau de bord même sans LilyGO.
5. Pour un LilyGO déjà configuré, utilise le même courtier qu’avant. Le préfixe par défaut est `mission_quota`.

### Installation locale et dépannage

- **Installation locale** — Télécharge le ZIP de la version souhaitée depuis les [versions GitHub](https://github.com/LoBidouille/Codex-HA-Quota/releases). Décompresse-le, copie le dossier `mission_quota_bridge` dans le partage local `addons` ou `local_apps`, puis actualise la boutique Home Assistant.
- **Jauges grises** — Vérifie la date du dernier relevé et la connexion MQTT. Si deux collecteurs utilisent le même courtier et les mêmes topics, arrête l’ancien. Un relevé périmé apparaît en gris sur le LilyGO.
- **Connexion expirée** — Relance la connexion par code depuis le panneau. En cas de coupure temporaire, le collecteur réessaie et conserve l’heure du dernier relevé.
- **Mise à jour ou retour arrière** — Fais une sauvegarde de l’application avant de la mettre à jour. Pour revenir à un ancien collecteur, arrête d’abord Mission Quota.

## English

### Connect ChatGPT

Start Mission Quota and open its web UI. Choose **Connecter mon compte ChatGPT** (Connect my ChatGPT account), then **Ouvrir OpenAI** (Open OpenAI). Sign in on the OpenAI page and enter the temporary code from the panel. Enter your password only on OpenAI’s site. If device-code sign-in is blocked, check your ChatGPT security settings or contact your workspace administrator.

Return to the panel and choose **Tester la lecture** (Test reading). The available windows and reset times appear when OpenAI returns a reading.

### Enable MQTT and the LilyGO

1. Check that **Mosquitto broker** and the MQTT integration are running in Home Assistant. Leave `mqtt_host` blank to use the discovered broker. For an external broker, enter its address, port, and credentials.
2. If another collector already publishes to the same topics, stop it and disable its automatic restart.
3. In **Configuration**, enable `publish_enabled`, save, and restart the app. The panel should show **Connecté** (Connected) for MQTT.
4. Under **Settings → Devices & services → MQTT**, open the **Mission Quota** device. Its four sensors provide the remaining percentages and reset times for both windows. You can add them to a dashboard without a LilyGO.
5. If your LilyGO is already configured, use the same broker. The default topic prefix is `mission_quota`.

### Local install and troubleshooting

- **Local install** — Download the ZIP for the version you want from [GitHub Releases](https://github.com/LoBidouille/Codex-HA-Quota/releases). Extract it, copy the `mission_quota_bridge` folder to the local `addons` or `local_apps` share, and refresh the Home Assistant app store.
- **Grey gauges** — Check the last reading and the MQTT connection. If two collectors use the same broker and topics, stop the old one. Stale readings appear grey on the LilyGO.
- **Expired session** — Run device-code sign-in again from the panel. During a temporary outage, the collector retries and keeps the previous reading’s timestamp.
- **Update or roll back** — Back up the app before an update. To return to a previous collector, stop Mission Quota first.

## Topics MQTT

| Topic | Usage / Purpose |
| --- | --- |
| `mission_quota/state` | Relevé pour le LilyGO / Reading for the LilyGO |
| `mission_quota/ha_state` | État des capteurs / Home Assistant sensor state |
| `mission_quota/availability` | Disponibilité du collecteur / Collector availability |
| `homeassistant/sensor/…/config` | Découverte des capteurs / Sensor discovery |
