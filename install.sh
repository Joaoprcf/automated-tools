sudo cp review.py /usr/local/bin/remote-review
sudo chmod +x /usr/local/bin/remote-review

sudo cp advice.py /usr/local/bin/advice
sudo chmod +x /usr/local/bin/advice

sudo cp prompt-advice.py /usr/local/bin/prompt-advice
sudo chmod +x /usr/local/bin/prompt-advice

SITE_PACKAGES=$(python3 -c 'import site; print(site.getsitepackages()[0])')
sudo cp prompt_utils.py $SITE_PACKAGES