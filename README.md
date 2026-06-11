# World Cup 2026 Predictor

A simulation dashboard for the FIFA World Cup 2026. Run simulations, track how win probabilities shift as the tournament progresses, and update the bracket with real results as matches are played.

## What does it do?

It simulates the World Cup thousands of times and tells you how likely each team is to win. As real matches are played, you can enter the results and re-run the simulation — the probabilities update to reflect what's actually happened.

## Setting it up

You'll need to do this once. It takes about 5 minutes.

### Step 1 — Open a terminal

**On Mac:** Press `Cmd + Space`, type "Terminal" and hit Enter.

**On Windows:** Press `Win + R`, type `cmd` and hit Enter. Or search for "Command Prompt" in the Start menu.

### Step 2 — Check you have Python installed

In the terminal, type:

**Mac:**
```bash
python3 --version
```

**Windows:**
```bash
python --version
```

If you see something like `Python 3.11.0` you're good. If you get an error, download Python from [python.org](https://www.python.org/downloads/) and install it. **On Windows, make sure to tick "Add Python to PATH"** during installation, then open a fresh Command Prompt and try again.

### Step 3 — Download the project

Run this to download the project to your computer (it will automatically create a `World-Cup-Predictor` folder):

```bash
git clone https://github.com/JoshDenning96/World-Cup-Predictor
```

If you get a "git not found" error on Windows, download Git from [git-scm.com](https://git-scm.com/download/win), install it, then open a fresh Command Prompt and try again.

Then move into the newly created folder:

```bash
cd World-Cup-Predictor
```

### Step 4 — Install the required packages

**Mac:**
```bash
pip3 install -r requirements.txt
```

**Windows:**
```bash
pip install -r requirements.txt
```

This downloads a few Python libraries the project needs. It only takes a minute.

### Step 5 — Start the server

**Mac:**
```bash
python3 server.py
```

**Windows:**
```bash
python server.py
```

You should see something like `Serving website at http://127.0.0.1:8000`. Leave this terminal window open — it needs to keep running.

### Step 6 — Open the dashboard

Open your browser and go to:

**[http://127.0.0.1:8000](http://127.0.0.1:8000)**

That's it! You should see the dashboard.

---

> **Next time** you want to use it, you only need Steps 5 and 6 — open a terminal, navigate to the folder (`cd World-Cup-Predictor`) and start the server.

---

## How to use it

**Running a simulation:**
Click **Run simulation** at the top of the page. You can choose how many simulations to run — more simulations = more accurate probabilities but takes a bit longer. 200–500 is a good balance.

**Entering real results:**
1. Switch the mode dropdown from **Full simulation** to **Actuals + simulation**
2. An actuals panel will appear — use the tabs to navigate between groups (A–L) and knockout rounds (R32, R16, etc.)
3. Enter scores for group matches, or click the winning team for knockout matches
4. Click **Run simulation** to re-simulate the tournament from the current state

Bracket positions confirmed by actual results are shown with a green dot.

## How it works

Match outcomes are determined using FIFA Elo ratings. The rating difference between two teams sets the win/draw/loss probabilities for each simulated match. Knockout draws are resolved as a 50/50 coin flip (simulating a penalty shootout). A −45 Elo point adjustment is applied by default to all qualified CONMEBOL teams.

## License

MIT
