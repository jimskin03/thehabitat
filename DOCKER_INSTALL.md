# Install the Docker Compose plugin (Ubuntu/Debian)

Use this when `sudo apt install docker-compose-plugin` fails with "Unable to locate package". That means Docker's official apt repository is not set up yet. Run the commands below in order, one at a time.

Note: if this machine is Debian instead of Ubuntu, replace "ubuntu" with "debian" in the gpg URL (step 4) and in the deb line (step 6).

1. Refresh the package list:

```
sudo apt-get update
```

2. Install the tools needed to download and verify Docker's key:

```
sudo apt-get install ca-certificates curl
```

3. Create the folder that holds apt signing keys:

```
sudo install -m 0755 -d /etc/apt/keyrings
```

4. Download Docker's official signing key:

```
sudo curl -fsSL https://download.docker.com/linux/ubuntu/gpg -o /etc/apt/keyrings/docker.asc
```

5. Make the key readable by apt:

```
sudo chmod a+r /etc/apt/keyrings/docker.asc
```

6. Add Docker's repository to apt (this is one single line):

```
echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.asc] https://download.docker.com/linux/ubuntu $(. /etc/os-release && echo "$VERSION_CODENAME") stable" | sudo tee /etc/apt/sources.list.d/docker.list > /dev/null
```

7. Refresh the package list again so apt sees the new repository:

```
sudo apt-get update
```

8. Install the Docker Compose plugin:

```
sudo apt-get install docker-compose-plugin
```

9. Check that it works:

```
docker compose version
```
