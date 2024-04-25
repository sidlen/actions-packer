import atexit
import ssl
import requests
import hcl2
import argparse
import os
import json
import hvac
from pyVim.connect import SmartConnect, Disconnect
from pyVmomi import vim
from vmware.vapi.vsphere.client import create_vsphere_client

def vaultSecret(secret_path, secret_data, vault_addr, vault_token):
  vault_url = vault_addr
  vault_token = vault_token
  kv = "packer"
  client = hvac.Client(url=vault_url, token=vault_token)
  if client.is_authenticated():
    print("Успешная аутентификация в Vault.")
    create_secret_response = client.secrets.kv.v2.create_or_update_secret(
      path=secret_path,
      secret=secret_data,
      mount_point=kv,
    )
    print(f"Секрет успешно создан: {create_secret_response}")
    ui_url = f"{vault_url}/ui/vault/secrets/{kv}/show/{secret_path}"
    print(f"Секрет доступен по URL: {ui_url}")
  else:
    print("Ошибка аутентификации в Vault.")
  return ui_url

def uploadHCLVars(input_file):
  with open(input_file, 'r') as file:
    return hcl2.load(file)

def uploadManifest(input_file):
  with open(input_file, 'r') as file:
    return json.load(file)

def get_obj(content, vimtype, name):
  obj = None
  container = content.viewManager.CreateContainerView(content.rootFolder, vimtype, True)
  for c in container.view:
    if c.name == name:
      obj = c
      break
  container.Destroy()
  return obj

def getVM(vm_name, vc_data):
  context = ssl._create_unverified_context()
  service_instance = SmartConnect(host=vc_data["vc_host"], user=vc_data["vc_user"], pwd=vc_data["vc_password"], sslContext=context)
  atexit.register(Disconnect, service_instance)
  content = service_instance.RetrieveContent()
  vm = get_obj(content, [vim.VirtualMachine], vm_name)
  return vm

def vc_cliet(vc_data):
  requests.packages.urllib3.disable_warnings()
  session = requests.session()
  session.verify = False
  vsphere_client = create_vsphere_client(server=vc_data["vc_host"], username=vc_data["vc_user"], password=vc_data["vc_password"], session=session)
  return vsphere_client

def get_tag_id_by_name(vsphere_client, tag_name):
  tag_list = vsphere_client.tagging.Tag.list()
  for tag_id in tag_list:
    tag = vsphere_client.tagging.Tag.get(tag_id)
    if tag.name == tag_name:
      return tag_id
  return None

def add_notes_to_vm(vm, notes):
  spec = vim.vm.ConfigSpec()
  spec.annotation = notes
  task = vm.ReconfigVM_Task(spec)
  try:
    # Ожидание завершения задачи
    while task.info.state not in [vim.TaskInfo.State.success, vim.TaskInfo.State.error]:
      pass
    if task.info.state == vim.TaskInfo.State.success:
      print(f"Заметки успешно добавлены к VM: {vm.name}")
    else:
      print("Ошибка при добавлении заметок к VM")
  except Exception as e:
    print(f"Произошла ошибка при добавлении заметок: {e}")

def main():
  packer_variables_file_path = os.getenv("PACKER_VARIABLES_FILE_PATH")
  manifest_file_path = os.getenv("MANIFEST_FILE_PATH")
  vm_ssh_pwd = os.getenv('PKR_VAR_SSH_PASSWORD', 'password')
  vault_addr = os.getenv("VAULT_URL")
  vault_token = os.getenv("VAULT_TOKEN")
  vsphere_password = os.getenv('PKR_VAR_VCENTER_PASSWORD')
  project_url = os.getenv('NOTES_PROJECT_URL')
  autoinstall_config_url = os.getenv('NOTES_AUTOINSTALL_CONFIG_URL')
  
  hcl_data = uploadHCLVars(packer_variables_file_path)
  print(hcl_data)
  
  vc_data = {
    "vc_host": hcl_data["vcenter_server"],
    "vc_user": hcl_data["vcenter_user"].replace('\\\\','\\'),
    "vc_password": vsphere_password
  }
  print()
  print(vc_data)
  print()
  tags_ids = hcl_data["tags_ids"]
  tags_names = hcl_data["tags_names"]
  
  json_data = uploadManifest(manifest_file_path)
  print (json_data)
  
  vm_name = json_data["builds"][0]["artifact_id"]
  apt_packages = json_data["builds"][0]["custom_data"]["apt_packages"]
  build_date = json_data["builds"][0]["custom_data"]["build_date"]
  vm = getVM(vm_name, vc_data)
  

  vm_cred = {
    "user": hcl_data["ssh_user"],
    "password": vm_ssh_pwd
  }
  vault_url = vaultSecret(vm_name, vm_cred, vault_addr, vault_token)
  if vm:
    print(f"Виртуальная машина '{vm_name}' найдена.")
    vm_moid = vm._moId
    notes = "image build by packer\nbuild data: " + build_date + "\nproject url: " + project_url + "\nautoinstall config: " + autoinstall_config_url + "\nvm credentials: " + vault_url + "\npreinstalled packages:\n-" + apt_packages
    add_notes_to_vm(vm, notes)
    vsphere_client = vc_cliet(vc_data)
    tag_association = vsphere_client.tagging.TagAssociation
    if not tags_ids:
      for tag_name in tags_names:
        tag_id = get_tag_id_by_name(vsphere_client, tag_name)
        tag_association.attach(tag_id=tag_id, object_id={'id': vm_moid, 'type': 'VirtualMachine'})
    else:
      for tag_id in tags_ids:
        tag_association.attach(tag_id=tag_id, object_id={'id': vm_moid, 'type': 'VirtualMachine'})

  else:
    print(f"Виртуальная машина '{vm_name}' не найдена.")

if __name__ == "__main__":
  main()