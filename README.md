

# Generative Agents: Interactive Simulacra of Human Behavior 

<p align="center" width="100%">
<img src="cover.png" alt="Smallville" style="width: 80%; min-width: 300px; display: block; margin: auto;">
</p>

This repository accompanies our research paper titled "[Generative Agents: Interactive Simulacra of Human Behavior](https://arxiv.org/abs/2304.03442)." It contains our core simulation module for  generative agents—computational agents that simulate believable human behaviors—and their game environment. Below, we document the steps for setting up the simulation environment on your local machine and for replaying the simulation as a demo animation.

## Quick start with `start.sh`

`start.sh` replaces the old multi-terminal routine. One command starts the web server (Django, port 8000) and the reverie simulation server (`reverie.py`) in the background. You no longer open two terminals, activate the virtual environment in each one, or type reverie's two startup answers yourself.

**One-time setup** (the script does not install anything for you):

1. Create the Python 3.9 virtual environment and install the requirements, as in [Step 2. Install requirements.txt](#step-2-install-requirementstxt) below. By default `start.sh` looks for `environment/frontend_server/.venv`; set `VENV=/path/to/venv` to use another one.
2. Create `reverie/backend_server/utils.py` from `utils.py.example`, as in the setup steps below. `start.sh` stops with a clear message if it is missing.

**Each time you want to run it:**

1. From the repository root, run:

   ```bash
   ./start.sh
   ```

   It activates the virtual environment, starts both servers, prints the web address, and follows the logs. Press **Ctrl+C** to stop both servers.
2. Open the habitat web page at [http://127.0.0.1:8000/](http://127.0.0.1:8000/). To reach it from another device over Tailscale, start with `WEB_HOST=tailscale ./start.sh` and open the address it prints. See [Open the app from another device over Tailscale](#open-the-app-from-another-device-over-tailscale).
3. In installations with the Habitat interface, click **Settings**, enter your API key, and click **Save**, as described in [Enter an API key in the Habitat interface](#enter-an-api-key-in-the-habitat-interface). Otherwise the key comes from `utils.py`.
4. `reverie.py` is already running. `start.sh` started it with the web server, and saving a key in the web page does not start it. Send it commands with `./start.sh send "run 100"`.

Other commands and options:

| Command or option | What it does |
| --- | --- |
| `./start.sh send "run 100"` | Types a command into the running reverie prompt |
| `./start.sh logs` | Follows both logs from another terminal |
| `./start.sh stop` | Stops both servers from another terminal |
| `FORK_SIM`, `SIM_NAME` | Simulation to fork from (default `base_the_ville_isabella_maria_klaus`) and the name of the new run (default `habitat-<timestamp>`) |
| `WEB_PORT`, `WEB_HOST` | Web port (default 8000) and bind address (default `127.0.0.1`, or `tailscale` to use the Tailscale IP) |

Logs and process IDs are written to `.habitat-run/`, which is gitignored. In this background mode reverie's interactive `api ...` commands do not work; set the model in `utils.py` instead. This script has not been tested on every setup yet, so if it fails, the manual steps below still work.

The sections below keep the manual instructions, which are still valid if you prefer to run each server yourself.

## Docker

The `Dockerfile` and `docker-compose.yml` run the whole stack (the Django web server and `reverie.py`) in one container pinned to Python 3.9, so the host's own Python version does not matter. The container's only process is `start.sh`, which starts both servers and stops both when the container stops.

1. Create your `utils.py` from the example, on the host, before the first start (the image does not contain it, so your key is never baked into the image):

   ```bash
   cp reverie/backend_server/utils.py.example reverie/backend_server/utils.py
   ```

   Edit it and set your API key, as in [Step 1. Generate Utils File](#step-1-generate-utils-file). Without this file `docker compose up` stops with an error, because the file is mounted into the container read-only. `reverie.py` also cannot run without it.
2. From the repository root, build and start:

   ```bash
   docker compose up --build
   ```

   The first build installs the pinned dependencies and takes a while. Press **Ctrl+C** (or run `docker compose down` from another terminal) to stop both servers.
3. Open [http://localhost:8000/](http://localhost:8000/). The port is published on `127.0.0.1` only. To publish it on other interfaces, run `HABITAT_BIND=0.0.0.0 docker compose up` (the app runs with Django `DEBUG` on, so only do that on a network you trust).
4. In installations with the Habitat interface, click **Settings**, enter your API key, and click **Save**, as described in [Enter an API key in the Habitat interface](#enter-an-api-key-in-the-habitat-interface). Otherwise the key comes from `utils.py`. As with `start.sh`, saving a key does not start `reverie.py`; it is already running.

Useful commands while it runs:

| Command | What it does |
| --- | --- |
| `docker compose exec habitat ./start.sh send "run 100"` | Types a command into the running reverie prompt |
| `docker compose logs -f` | Follows the web and reverie logs |
| `docker compose down` | Stops and removes the container (data volumes are kept) |
| `docker compose down -v` | Also deletes the data volumes, including saved simulations |

Settings you can pass as environment variables, for example `SIM_NAME=my-run docker compose up`: `FORK_SIM` (simulation to fork from) and `SIM_NAME` (name of the new run; by default each start creates a new timestamped run).

Saved data lives in named volumes: `.habitat-run` (logs and PIDs) and the `storage`, `temp_storage` and `compressed_storage` folders under `environment/frontend_server`. A new volume starts with the repository's copy of its folder; after that, rebuilding the image does not overwrite it.

Notes: `WEB_HOST=tailscale` does not apply inside the container, which has no Tailscale; the compose file binds the web server to `0.0.0.0` inside the container and you control exposure with the published port. As with `start.sh`, reverie's interactive `api ...` commands do not work; set the model in `utils.py`.

## Start the app and connect

These steps are for an existing installation with dependencies installed in `environment/frontend_server/.venv`. If you are setting up a new installation, follow **Setting Up the Environment** below first. In the commands below, `<YOUR_PROJECT_DIR>` is the folder where you cloned this repository.

### Open the app on the server computer

1. Open a terminal on the computer that has the project installed.
2. Go to the folder containing `manage.py`:

   ```bash
   cd <YOUR_PROJECT_DIR>/environment/frontend_server
   ```

3. Start the server using the Python executable in the project's virtual environment:

   ```bash
   .venv/bin/python manage.py runserver
   ```

4. Leave that terminal open. On the **same computer**, open [http://localhost:8000/](http://localhost:8000/) in your browser.
5. To stop the server, press **Ctrl+C** in its terminal.

### Open the app from another device over Tailscale

`localhost` always refers to the device running your browser. To open the app from another device, use the server computer's Tailscale IP address and make Django listen on that address.

1. Connect both devices to the same Tailscale network.
2. In a terminal on the **server computer**, find its Tailscale IPv4 address:

   ```bash
   tailscale ip -4
   ```

   Use this address, shown below as `<YOUR_TAILSCALE_IP>`, in the commands and browser URL below.

3. If the server is already running, press **Ctrl+C** in its terminal to stop it.
4. Start it again, listening on its Tailscale address:

   ```bash
   cd <YOUR_PROJECT_DIR>/environment/frontend_server
   .venv/bin/python manage.py runserver <YOUR_TAILSCALE_IP>:8000
   ```

5. Leave the terminal open. On the **other device**, open [http://<YOUR_TAILSCALE_IP>:8000/](http://<YOUR_TAILSCALE_IP>:8000/). Use `http://` and include `:8000`.

When bound to the Tailscale address, use that address in browsers on either computer. The default `runserver` command listens on `127.0.0.1`, which only accepts connections from the server computer itself.

### Enter an API key in the Habitat interface

In installations with the Habitat single-page interface, open the root URL above, click **Settings** in the top right, paste your key into **API key**, and click **Save**. Set **API base** and **Model** to match your provider. If a key is already saved, you do not need to enter it again. Click **Play** below the map to watch the simulation.

Without a key, this interface plays the saved Smallville template. With a saved key, it requests new simulation steps from the configured model.

The Habitat interface changes are currently local to the installation described here and are not included in this README update. A checkout showing the original landing page uses the **Running a Simulation** instructions below, including the separate simulation server and `utils.py` API key configuration.

### Troubleshooting startup and connections

| Problem | What to do |
| --- | --- |
| `python: command not found` | Use `.venv/bin/python` from `environment/frontend_server`, as shown above. You do not need a system-wide `python` command. |
| `.ven/bin/python: No such file or directory` | The folder is **`.venv`**, with a final `v`. Run `.venv/bin/python manage.py runserver`. |
| `.venv/bin/python: No such file or directory` | Check that you are in `environment/frontend_server` and that `.venv` exists there. A virtual environment is created locally and is not supplied by a Git clone. If it is missing or its Python executable no longer exists, create/recreate it with a Python version compatible with the project's requirements, then install dependencies as described below. |
| `can't open file 'manage.py'` | Run the `cd` command above first; `manage.py` is in `environment/frontend_server`. |
| `No module named django` | Install the project dependencies into the environment used to run the server. From `environment/frontend_server`, use `.venv/bin/python -m pip install -r requirements.txt`. See the Python version note below. |
| `That port is already in use` | Another server is already using port 8000. If it is this app, open its browser URL. To change its listening address for Tailscale, stop the existing instance in its terminal with **Ctrl+C** before restarting it. |
| The page works on the server but not on another device | Restart with the server's Tailscale IP, as shown above. On the other device, use that IP in the browser, not `localhost` or `127.0.0.1`. |
| The Tailscale URL still times out | Confirm both devices are connected to Tailscale and the server terminal is still running. On the server, use `ss -ltnp` to check that port 8000 is listening on its Tailscale IP. Check that host firewall rules and Tailscale access rules allow the client to reach the server on TCP port 8000. |
| `Cannot assign requested address` | Run `tailscale ip -4` on the server again and use the address it reports. Make sure Tailscale is connected before starting Django on that address. |
| `DisallowedHost` or `Invalid HTTP_HOST header` | In `environment/frontend_server/frontend_server/settings/local.py`, ensure `ALLOWED_HOSTS` allows the server's Tailscale IP. For example, add your server's Tailscale IP (as a quoted string, e.g. `"<YOUR_TAILSCALE_IP>"`) to the list, without `http://` or `:8000`, and restart the server. |
| No **Settings** button | Open the root URL `/`. If it still shows the original landing page, your checkout does not include the Habitat interface; use the original simulation instructions below. |

## <img src="https://joonsungpark.s3.amazonaws.com:443/static/assets/characters/profile/Isabella_Rodriguez.png" alt="Generative Isabella">   Setting Up the Environment 
To set up your environment, you will need to generate a `utils.py` file that contains your OpenAI API key and download the necessary packages.

### Step 1. Generate Utils File
In the `reverie/backend_server` folder (where `reverie.py` is located), create a new file titled `utils.py` and copy and paste the content below into the file:
```
# Copy and paste your OpenAI API Key
openai_api_key = "<Your OpenAI API>"
# Put your name
key_owner = "<Name>"

maze_assets_loc = "../../environment/frontend_server/static_dirs/assets"
env_matrix = f"{maze_assets_loc}/the_ville/matrix"
env_visuals = f"{maze_assets_loc}/the_ville/visuals"

fs_storage = "../../environment/frontend_server/storage"
fs_temp_storage = "../../environment/frontend_server/temp_storage"

collision_block_id = "32125"

# Verbose 
debug = True

# Optional named APIs. The reverie prompt can switch among these
# without restarting. Delete this block to keep a single OpenAI key.
# apis = {
#   "openai": {
#     "kind": "openai",
#     "mode": "chat",
#     "api_key": openai_api_key,
#     "api_base": "https://api.openai.com/v1",
#     "model": "gpt-4o-mini",
#     "embedding_model": "text-embedding-ada-002",
#   },
#   "ollama": {
#     "kind": "openai",
#     "mode": "chat",
#     "api_key": "ollama",
#     "api_base": "http://127.0.0.1:11434/v1",
#     "model": "llama3.1",
#     "embedding_model": "nomic-embed-text",
#     "embedding_api": "openai",
#   },
# }
# active_api = "openai"
```
Replace `<Your OpenAI API>` with your OpenAI API key, and `<name>` with your name. `reverie/backend_server/utils.py.example` is the same file with the optional `apis` block turned on.
 
### Step 2. Install requirements.txt
Install everything listed in the `requirements.txt` file (I strongly recommend first setting up a virtualenv as usual). A note on Python version: we tested our environment on Python 3.9.12. 

To create the `.venv` used by the startup commands above, run these commands from the repository root with Python 3.9 installed:

```bash
cd environment/frontend_server
python3.9 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
```

Skip creating the environment if `.venv` already exists and works. The pinned dependencies are old; installing them with a newer system Python can fail. When following the original two-server instructions below, activate this virtual environment in each terminal before running the `python` commands:

```bash
source <YOUR_PROJECT_DIR>/environment/frontend_server/.venv/bin/activate
```

Use your own checkout path if different. Activation makes `python` refer to the environment's executable even when the system has only `python3`.

## <img src="https://joonsungpark.s3.amazonaws.com:443/static/assets/characters/profile/Klaus_Mueller.png" alt="Generative Klaus">   Running a Simulation 
To run a new simulation, you will need to concurrently start two servers: the environment server and the agent simulation server.

### Step 1. Starting the Environment Server
Again, the environment is implemented as a Django project, and as such, you will need to start the Django server. To do this, first navigate to `environment/frontend_server` (this is where `manage.py` is located) in your command line. Then run the following command:

    python manage.py runserver

Then, on your favorite browser, go to [http://localhost:8000/](http://localhost:8000/). If you see a message that says, "Your environment server is up and running," your server is running properly. Ensure that the environment server continues to run while you are running the simulation, so keep this command-line tab open! (Note: I recommend using either Chrome or Safari. Firefox might produce some frontend glitches, although it should not interfere with the actual simulation.)

### Step 2. Starting the Simulation Server
Open up another command line (the one you used in Step 1 should still be running the environment server, so leave that as it is). Navigate to `reverie/backend_server` and run `reverie.py`.

    python reverie.py
This will start the simulation server. A command-line prompt will appear, asking the following: "Enter the name of the forked simulation: ". To start a 3-agent simulation with Isabella Rodriguez, Maria Lopez, and Klaus Mueller, type the following:
    
    base_the_ville_isabella_maria_klaus
The prompt will then ask, "Enter the name of the new simulation: ". Type any name to denote your current simulation (e.g., just "test-simulation" will do for now).

    test-simulation
Keep the simulator server running. At this stage, it will display the following prompt: "Enter option: "

### Step 3. Running and Saving the Simulation
On your browser, navigate to [http://localhost:8000/simulator_home](http://localhost:8000/simulator_home). You should see the map of Smallville, along with a list of active agents on the map. You can move around the map using your keyboard arrows. Please keep this tab open. To run the simulation, type the following command in your simulation server in response to the prompt, "Enter option":

    run <step-count>
Note that you will want to replace `<step-count>` above with an integer indicating the number of game steps you want to simulate. For instance, if you want to simulate 100 game steps, you should input `run 100`. One game step represents 10 seconds in the game.


Your simulation should be running, and you will see the agents moving on the map in your browser. Once the simulation finishes running, the "Enter option" prompt will re-appear. At this point, you can simulate more steps by re-entering the run command with your desired game steps, exit the simulation without saving by typing `exit`, or save and exit by typing `fin`.

The saved simulation can be accessed the next time you run the simulation server by providing the name of your simulation as the forked simulation. This will allow you to restart your simulation from the point where you left off.

### Switching the LLM API while the server is running

Every model call reads the active API at that moment. At `Enter option:`, or during `run` (type the command and press Enter; the next model call uses it):

```
api
api list
api mode chat
api model gpt-4o-mini
api add ollama http://127.0.0.1:11434/v1 llama3.1 ollama
api ollama
api key <another-key>
api help
```

`mode completion` is the original behavior: prompts call the legacy Completions API with the engine stored on each prompt (`text-davinci-002` or `text-davinci-003`). `mode chat` sends that same prompt to the active chat model. Use chat mode for current OpenAI models and for any server with an OpenAI-compatible chat API (Ollama, vLLM, LM Studio, Groq, OpenRouter, Azure).

A switch lasts until `reverie.py` exits. To keep named profiles across restarts, uncomment `apis` and `active_api` in `utils.py`. `api add` against a non-OpenAI base leaves embeddings on an OpenAI profile when one is configured. `api embedding <model>` or `api embedding-from <name>` changes that.

A line typed during `run` that is not an `api` command waits and runs when `Enter option:` returns.

### Step 4. Replaying a Simulation
You can replay a simulation that you have already run simply by having your environment server running and navigating to the following address in your browser: `http://localhost:8000/replay/<simulation-name>/<starting-time-step>`. Please make sure to replace `<simulation-name>` with the name of the simulation you want to replay, and `<starting-time-step>` with the integer time-step from which you wish to start the replay.

For instance, by visiting the following link, you will initiate a pre-simulated example, starting at time-step 1:  
[http://localhost:8000/replay/July1_the_ville_isabella_maria_klaus-step-3-20/1/](http://localhost:8000/replay/July1_the_ville_isabella_maria_klaus-step-3-20/1/)

### Step 5. Demoing a Simulation
You may have noticed that all character sprites in the replay look identical. We would like to clarify that the replay function is primarily intended for debugging purposes and does not prioritize optimizing the size of the simulation folder or the visuals. To properly demonstrate a simulation with appropriate character sprites, you will need to compress the simulation first. To do this, open the `compress_sim_storage.py` file located in the `reverie` directory using a text editor. Then, execute the `compress` function with the name of the target simulation as its input. By doing so, the simulation file will be compressed, making it ready for demonstration.

To start the demo, go to the following address on your browser: `http://localhost:8000/demo/<simulation-name>/<starting-time-step>/<simulation-speed>`. Note that `<simulation-name>` and `<starting-time-step>` denote the same things as mentioned above. `<simulation-speed>` can be set to control the demo speed, where 1 is the slowest, and 5 is the fastest. For instance, visiting the following link will start a pre-simulated example, beginning at time-step 1, with a medium demo speed:  
[http://localhost:8000/demo/July1_the_ville_isabella_maria_klaus-step-3-20/1/3/](http://localhost:8000/demo/July1_the_ville_isabella_maria_klaus-step-3-20/1/3/)

### Tips
If an API key hits a rate limit, switch from the reverie prompt with `api key <other-key>` or `api <name>` and keep the same run. Calls wait at most the active timeout (120 seconds unless you set `api timeout` or `request_timeout` on the profile), so a hung request returns and the next call can use the API you just selected. Saving often is still worth doing. Simulations can be costly when many agents are in the environment.

## <img src="https://joonsungpark.s3.amazonaws.com:443/static/assets/characters/profile/Maria_Lopez.png" alt="Generative Maria">   Simulation Storage Location
All simulations that you save will be located in `environment/frontend_server/storage`, and all compressed demos will be located in `environment/frontend_server/compressed_storage`. 

## <img src="https://joonsungpark.s3.amazonaws.com:443/static/assets/characters/profile/Sam_Moore.png" alt="Generative Sam">   Customization

There are two ways to optionally customize your simulations. 

### Author and Load Agent History
First is to initialize agents with unique history at the start of the simulation. To do this, you would want to 1) start your simulation using one of the base simulations, and 2) author and load agent history. More specifically, here are the steps:

#### Step 1. Starting Up a Base Simulation 
There are two base simulations included in the repository: `base_the_ville_n25` with 25 agents, and `base_the_ville_isabella_maria_klaus` with 3 agents. Load one of the base simulations by following the steps until step 2 above. 

#### Step 2. Loading a History File 
Then, when prompted with "Enter option: ", you should load the agent history by responding with the following command:

    call -- load history the_ville/<history_file_name>.csv
Note that you will need to replace `<history_file_name>` with the name of an existing history file. There are two history files included in the repo as examples: `agent_history_init_n25.csv` for `base_the_ville_n25` and `agent_history_init_n3.csv` for `base_the_ville_isabella_maria_klaus`. These files include semicolon-separated lists of memory records for each of the agents—loading them will insert the memory records into the agents' memory stream.

#### Step 3. Further Customization 
To customize the initialization by authoring your own history file, place your file in the following folder: `environment/frontend_server/static_dirs/assets/the_ville`. The column format for your custom history file will have to match the example history files included. Therefore, we recommend starting the process by copying and pasting the ones that are already in the repository.

### Create New Base Simulations
For a more involved customization, you will need to author your own base simulation files. The most straightforward approach would be to copy and paste an existing base simulation folder, renaming and editing it according to your requirements. This process will be simpler if you decide to keep the agent names unchanged. However, if you wish to change their names or increase the number of agents that the Smallville map can accommodate, you might need to directly edit the map using the [Tiled](https://www.mapeditor.org/) map editor.


## <img src="https://joonsungpark.s3.amazonaws.com:443/static/assets/characters/profile/Eddy_Lin.png" alt="Generative Eddy">   Authors and Citation 

**Authors:** Joon Sung Park, Joseph C. O'Brien, Carrie J. Cai, Meredith Ringel Morris, Percy Liang, Michael S. Bernstein

Please cite our paper if you use the code or data in this repository. 
```
@inproceedings{Park2023GenerativeAgents,  
author = {Park, Joon Sung and O'Brien, Joseph C. and Cai, Carrie J. and Morris, Meredith Ringel and Liang, Percy and Bernstein, Michael S.},  
title = {Generative Agents: Interactive Simulacra of Human Behavior},  
year = {2023},  
publisher = {Association for Computing Machinery},  
address = {New York, NY, USA},  
booktitle = {In the 36th Annual ACM Symposium on User Interface Software and Technology (UIST '23)},  
keywords = {Human-AI interaction, agents, generative AI, large language models},  
location = {San Francisco, CA, USA},  
series = {UIST '23}
}
```

## <img src="https://joonsungpark.s3.amazonaws.com:443/static/assets/characters/profile/Wolfgang_Schulz.png" alt="Generative Wolfgang">   Acknowledgements

We encourage you to support the following three amazing artists who have designed the game assets for this project, especially if you are planning to use the assets included here for your own project: 
* Background art: [PixyMoon (@_PixyMoon\_)](https://twitter.com/_PixyMoon_)
* Furniture/interior design: [LimeZu (@lime_px)](https://twitter.com/lime_px)
* Character design: [ぴぽ (@pipohi)](https://twitter.com/pipohi)

In addition, we thank Lindsay Popowski, Philip Guo, Michael Terry, and the Center for Advanced Study in the Behavioral Sciences (CASBS) community for their insights, discussions, and support. Lastly, all locations featured in Smallville are inspired by real-world locations that Joon has frequented as an undergraduate and graduate student---he thanks everyone there for feeding and supporting him all these years.


