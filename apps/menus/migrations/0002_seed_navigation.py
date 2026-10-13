from django.db import migrations

def seed(apps,schema_editor):
    Menu=apps.get_model('menus','Menu')
    db=schema_editor.connection.alias
    root,_=Menu.objects.using(db).get_or_create(code='safety',defaults={'title':'안전관리','order':10})
    ops,_=Menu.objects.using(db).get_or_create(code='operations',defaults={'title':'감지·기록','parent':root,'order':10})
    lab,_=Menu.objects.using(db).get_or_create(code='lab',defaults={'title':'분석·모델','parent':root,'order':20,'staff_only':True})
    config,_=Menu.objects.using(db).get_or_create(code='config',defaults={'title':'시스템 설정','order':20})
    items=[('monitor','실시간 감지','/monitor/',ops,False),('events','낙상 기록','/events/',ops,False),('jobs','영상 분석·모델 학습','/jobs/',lab,True),('models','모델 적용·비교','/models/',lab,True),('settings','감지 기준','/settings/',config,True),('notifications','알림 연결','/notifications/',config,False)]
    for index,(code,title,url,parent,staff) in enumerate(items):
        Menu.objects.using(db).get_or_create(code=code,defaults={'title':title,'url':url,'parent':parent,'staff_only':staff,'order':index})
class Migration(migrations.Migration):
    dependencies=[('menus','0001_initial')]
    operations=[migrations.RunPython(seed,migrations.RunPython.noop)]
