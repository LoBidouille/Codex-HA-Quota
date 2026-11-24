# Mission Quota · Codex-HA-Quota

[Français](#français) · [English](#english)

## Français

Mission Quota suit les **quotas Codex de ton abonnement ChatGPT** sur Home Assistant OS. Il affiche le pourcentage restant et la prochaine recharge pour chaque fenêtre fournie par Codex. Tu peux utiliser les capteurs Home Assistant, un **LilyGO T-Display S3**, ou les deux.

### Comment ça marche

1. Depuis le panneau Mission Quota, tu connectes ton compte ChatGPT avec un code à usage unique sur le site d’OpenAI. Codex conserve la session dans les données privées de l’application.
2. Home Assistant OS lit les quotas toutes les cinq minutes par défaut. Selon ton compte, Codex peut fournir une fenêtre de **5 heures** et une fenêtre **hebdomadaire**. Le panneau affiche les fenêtres reçues. Les limites des conversations ChatGPT classiques varient selon le modèle et l’abonnement et ne figurent pas dans ces relevés.
3. Après activation de MQTT, Mission Quota publie les relevés sur Mosquitto. Home Assistant crée les capteurs par découverte MQTT et le LilyGO récupère ses jauges sur le même courtier. Le Raspberry Pi assure la collecte même lorsque le Mac est éteint.

### Installation

1. Dans Home Assistant OS, ouvre **Paramètres → Applications → Installer une application** puis **⋮ → Dépôts**.
2. Ajoute `https://github.com/LoBidouille/Codex-HA-Quota`, sélectionne **Mission Quota**, puis clique sur **Installer**. Home Assistant construit l’image lors de la première installation.
3. Démarre l’application et ouvre son interface Web. Clique sur **Connecter mon compte ChatGPT**, puis saisis le code temporaire sur la page OpenAI.
4. Clique sur **Tester la lecture**. Pour alimenter les capteurs et le LilyGO, active ensuite `publish_enabled` dans la configuration. Laisse `mqtt_host` vide pour utiliser le courtier Mosquitto détecté par Home Assistant.

La version 1.1.0 a été testée sur Raspberry Pi 4 ARM64 sous Home Assistant OS. Le paquet inclut une cible AMD64 dont l’exécution reste à valider.

[Guide détaillé, connexion, dépannage et installation locale](mission_quota_bridge/DOCS.md#français)

## English

Mission Quota tracks the **Codex quotas included in your ChatGPT subscription** on Home Assistant OS. It shows the remaining percentage and next reset for each window returned by Codex. You can use Home Assistant sensors, a **LilyGO T-Display S3**, or both.

### How it works

1. Open the Mission Quota panel and sign in to ChatGPT with a one-time code on OpenAI’s site. Codex keeps the session in the app’s private storage.
2. Home Assistant OS reads the quotas every five minutes by default. Depending on your account, Codex may provide a **five-hour** window and a **weekly** window. The panel displays the windows it receives. Limits for regular ChatGPT conversations vary by model and subscription and are outside these readings.
3. After you enable MQTT publishing, Mission Quota sends readings to Mosquitto. Home Assistant creates sensors through MQTT discovery, and the LilyGO gets its readings from the same broker. Your Raspberry Pi keeps collecting while your Mac is off.

### Installation

1. In Home Assistant OS, open **Settings → Apps → Install app**, then **⋮ → Repositories**.
2. Add `https://github.com/LoBidouille/Codex-HA-Quota`, select **Mission Quota**, and choose **Install**. Home Assistant builds the image on first install.
3. Start the app and open its web UI. Choose **Connecter mon compte ChatGPT** and enter the one-time code on the OpenAI page.
4. Choose **Tester la lecture** to check the reading. To feed the sensors and LilyGO, enable `publish_enabled` in the app configuration. Leave `mqtt_host` blank to use the Mosquitto broker discovered by Home Assistant.

Version 1.1.0 was tested on a Raspberry Pi 4 running ARM64 Home Assistant OS. The package also targets AMD64, which still needs a runtime test.

[Detailed guide, sign-in, troubleshooting, and local installation](mission_quota_bridge/DOCS.md#english)
