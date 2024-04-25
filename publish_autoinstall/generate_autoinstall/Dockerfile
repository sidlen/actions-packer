FROM git.softline.com/registry/python-image:v1
COPY jinja.py /jinja.py
ENTRYPOINT ["sh", "-c", "echo \"::set-output name=firmware::$(python /jinja.py)\" && echo \"::set-output name=result::$(cat user-data)\""]