
from penshot.neopen.task.task_manager import TaskManager
from penshot.neopen.shot_config import ShotConfig

print('TaskManager simple smoke test')
manager = TaskManager()

# create with dict config
cfg1 = {'max_fragment_duration': 5.0}
tid1 = manager.create_task('script one', cfg1, task_id='t1')
print('created t1:', tid1)

# create with ShotConfig
conf2 = ShotConfig()
conf2.default_shot_duration = 2.2
tid2 = manager.create_task('script two', conf2, task_id='t2')
print('created t2:', tid2)

# list tasks
print('list_tasks:', manager.list_tasks())

# set callback
ok = manager.set_task_callback('t1', 'https://example.com/cb')
print('set callback t1:', ok, 'callback stored:', manager.get_task('t1').get('callback_url'))

# update progress
manager.update_task_progress('t1', 'parsing', 30)
print('t1 after progress:', manager.get_task('t1')['progress'], manager.get_task('t1')['stage'])

# update partial result
manager.update_task_result('t1', {'partial': 123})
print('t1 result after partial:', manager.get_task('t1')['result'])

# complete task
manager.complete_task('t1', {'success': True, 'data': {'shots': []}})
print('t1 after complete:', manager.get_task('t1')['status'], 'completed_at:', manager.get_task('t1').get('completed_at'))

# fail task t2
manager.fail_task('t2', 'some error')
print('t2 after fail:', manager.get_task('t2')['status'], 'error:', manager.get_task('t2')['error'])

# metrics
print('metrics:', manager.metrics)

# find tasks by status
print('find completed:', manager.find_tasks(status='completed'))
print('find failed:', manager.find_tasks(status='failed'))

# export/import snapshot
snap = manager.export_task_snapshot('t1')
print('snapshot keys:', list(snap.keys()))
new_tid = manager.import_task_snapshot(snap)
print('imported snapshot as', new_tid)
print('tasks after import:', manager.list_tasks())

# bulk delete
deleted = manager.bulk_delete(['t1', 't2', new_tid])
print('bulk deleted count:', deleted)
print('remaining tasks:', manager.list_tasks())

print('smoke test done')

