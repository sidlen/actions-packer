import hcl2
import os
from jinja2 import Environment, FileSystemLoader
from passlib.hash import sha512_crypt

def mask_to_cidr(mask):
  return sum([bin(int(x)).count('1') for x in mask.split('.')])

def render_jinja_template(template_path, output_path, variables):
  env = Environment(loader=FileSystemLoader('.'))
  template = env.get_template(template_path)
  output = template.render(variables)
  with open(output_path, 'w') as file:
      file.write(output)

def main():
  packer_variables_file_path = os.getenv("PACKER_VARIABLES_FILE_PATH")
  autoinstall_template_file_path = os.getenv("AUTOINSTALL_TEMPLATE_FILE_PATH")
  user_data = os.getenv("USER_DATA")
  with open(packer_variables_file_path, 'r') as file:
    hcl_data = hcl2.load(file)

  hcl_data["ssh_password"] = sha512_crypt.hash(os.getenv('PKR_VAR_SSH_PASSWORD', 'password'))
  hcl_data["network"]["mask"] = mask_to_cidr(hcl_data["network"]["mask"])
  render_jinja_template(autoinstall_template_file_path, user_data, hcl_data)
  print(hcl_data["FIRMWARE"])

if __name__ == "__main__":
  main()
