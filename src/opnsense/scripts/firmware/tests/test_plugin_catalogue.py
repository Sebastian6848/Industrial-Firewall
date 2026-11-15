import os,subprocess,tempfile,unittest
from pathlib import Path
SOURCE=Path(__file__).resolve().parents[1] / 'query.sh'
class CatalogueRegression(unittest.TestCase):
 def test_listings_never_refresh_and_do_not_hide_installed_plugins_offline(self):
  with tempfile.TemporaryDirectory() as tmp:
   p=Path(tmp)
   (p/'config.sh').write_text('PKG="'+str(p/'pkg')+'"\n')
   (p/'pkg').write_text('#!/bin/sh\nprintf "%s\\n" "$*" >> "'+str(p/'calls')+'"\ncase "$1" in\nrquery) case "$*" in *"%At"*) echo "os-test|||product_tier|||3";; *) echo "os-test|||1.0|||Test|||1B|||0|||0|||BSD|||OPNsense|||opnsense/os-test";; esac;;\nupdate) exit 1;;\nesac\n')
   (p/'pkg').chmod(0o755)
   (p/'query.sh').write_text(SOURCE.read_text().replace('/usr/local/opnsense/scripts/firmware/config.sh',str(p/'config.sh')))
   for action in ['remote','tiers']:
    r=subprocess.run(['sh',str(p/'query.sh'),action],capture_output=True,text=True,check=True)
    self.assertIn('os-test|||',r.stdout)
   calls=(p/'calls').read_text().splitlines()
   self.assertEqual(len(calls),2)
   self.assertTrue(all(line.startswith('rquery -U ') for line in calls))
 def test_failed_refresh_is_reported_not_returned_as_empty_catalogue(self):
  with tempfile.TemporaryDirectory() as tmp:
   p=Path(tmp);(p/'config.sh').write_text('PKG=/usr/bin/false\n')
   (p/'query.sh').write_text(SOURCE.read_text().replace('/usr/local/opnsense/scripts/firmware/config.sh',str(p/'config.sh')))
   result=subprocess.run(['sh',str(p/'query.sh'),'refresh'],capture_output=True,text=True,check=True)
   self.assertIn('CATALOGUE_REFRESH_FAILED',result.stdout)
if __name__=='__main__':unittest.main()
