from django import template 
register = template.Library() 

@register.filter 
def multiply(value, arg):
	if value == "" or arg == "": return 0.0
	return str(float(value) * float(arg))

@register.filter 
def add(value, arg):
	return str(float(value if value else 0) + float(arg if arg else 0))
