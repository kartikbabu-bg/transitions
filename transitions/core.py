from functools import partial
from collections import defaultdict

def listify(obj):
    return obj if isinstance(obj, list) or obj is None else [obj]


class State(object):

    def __init__(self, name, on_enter=None, on_exit=None):
        """
        Args:
            name (string): The name of the state
            on_enter (string, list): Optional callable(s) to trigger when a state 
                is entered. Can be either a string providing the name of a callable, 
                or a list of strings.
            on_exit (string, list): Optional callable(s) to trigger when a state 
                is exited. Can be either a string providing the name of a callable, 
                or a list of strings.
        """
        self.name = name
        self.on_enter = listify(on_enter) if on_enter else []
        self.on_exit = listify(on_exit) if on_exit else []

    def enter(self, event):
        """ Triggered when a state is entered. """
        for oe in self.on_enter: getattr(event.model, oe)()

    def exit(self, event):
        """ Triggered when a state is exited. """
        for oe in self.on_exit: getattr(event.model, oe)()

    def add_callback(self, trigger, func):
        """ Add a new enter or exit callback.
        Args:
            trigger (string): The type of triggering event. Must be one of 
                'enter' or 'exit'.
            func (string): The name of the callback function.
        """
        callback_list = getattr(self, 'on_' + trigger)
        callback_list.append(func)


class Transition(object):

    def __init__(self, source, dest, conditions=None, before=None, after=None):
        """
        Args:
            source (string): The name of the source State.
            dest (string): The name of the destination State.
            conditions (string, list): Condition(s) that must pass in order for 
                the transition to take place. Either a list providing the name 
                of a callable, or a list of callables. For the transition to 
                occur, ALL callables must return True.
            before (string or list): callbacks to trigger before the transition.
            after (string or list): callbacks to trigger after the transition.
        """
        self.source = source
        self.dest = dest
        self.before = [] if before is None else listify(before)
        self.after = [] if after is None else listify(after)
        
        self.conditions = [] if conditions is None else listify(conditions)

    def execute(self, event_data):
        """ Execute the transition.
        Args:
            event: An instance of class EventData.
        """
        machine = event_data.machine
        for c in self.conditions:
            if not getattr(event_data.model, c)(): return False

        for func in self.before: getattr(event_data.model, func)()
        machine.get_state(self.source).exit(event_data)
        machine.set_state(self.dest)
        event_data.update()
        machine.get_state(self.dest).enter(event_data)
        for func in self.after: getattr(event_data.model, func)()
        return True

    def add_callback(self, trigger, func):
        """ Add a new before or after callback.
        Args:
            trigger (string): The type of triggering event. Must be one of 
                'before' or 'after'.
            func (string): The name of the callback function.
        """
        callback_list = getattr(self, trigger)
        callback_list.append(func)


class EventData(object):

    def __init__(self, state, event, machine, model, *args, **kwargs):
        """
        Args:
            state (State): The State from which the Event was triggered.
            event (Event): The triggering Event.
            machine (Machine): The current Machine instance.
            model (object): The model/object the machine is bound to.
            args and kwargs: Optional positional or named arguments that 
                will be stored internally for possible later use.
                Positional arguments will be stored in self.args;
                named arguments will be set as attributes in self.
        """
        self.state = state
        self.event = event
        self.machine = machine
        self.model = model
        self.args = args
        for k, v in kwargs.items():
            setattr(self, k, v)

    def update(self):
        """ Updates the current State to accurately reflect the Machine. """
        self.state = self.machine.current_state


class Event(object):

    def __init__(self, name, machine):
        """
        Args:
            name (string): The name of the event, which is also the name of the 
                triggering callable (e.g., 'advance' implies an advance() method).
            machine (Machine): The current Machine instance.
        """
        self.name = name
        self.machine = machine
        self.transitions = defaultdict(list)

    def add_transition(self, transition):
        """ Add a transition to the list of potential transitions.
        Args:
            transition (Transition): The Transition instance to add to the list.
        """
        source = transition.source
        self.transitions[transition.source].append(transition)

    def trigger(self, *args, **kwargs):
        """ Serially execute all transitions that match the current state, 
        halting as soon as one successfully completes. 
        Args:
            args and kwargs: Optional positional or named arguments that 
                will be passed onto the EventData object, enabling arbitrary 
                state information to be passed on to downstream triggered 
                functions. """
        state_name = self.machine.current_state.name
        if state_name not in self.transitions:
            raise MachineError("Can't trigger event %s from state %s!" % (self.name, state_name))
        event = EventData(self.machine.current_state, self, self.machine, self.machine.model, *args, **kwargs)
        for t in self.transitions[state_name]:
            if t.execute(event): return True
        return False


class Machine(object):

    def __init__(self, model=None, states=None, initial=None, transitions=None, send_event=False):
        """
        Args:
            model (object): The object whose states we want to manage. If None, the current 
                Machine instance will be used the model (i.e., all triggering events will be 
                attached to the Machine itself).
            states (list): A list of valid states. Each element can be either a string or a 
                State instance. If string, a new generic State instance will be created that 
                has the same name as the string.
            initial (string): The initial state of the Machine.
            transitions (list): An optional list of transitions. Each element is a dictionary 
                of named arguments to be passed onto the Transition initializer.
        """
        self.model = self if model is None else model 
        self.states = {}
        self.events = {}
        self.current_state = None
        self.send_event = send_event
        
        if states is not None:
            states = listify(states)
            for s in states:
                if isinstance(s, basestring):
                    s = State(s)
                self.states[s.name] = s
                setattr(self.model, 'is_%s' % s.name, partial(self.is_state, s.name))

        self.set_state(initial)

        if transitions is not None:
            for t in transitions: self.add_transition(**t)

    def is_state(self, state):
        """ Check whether the current state matches the named state. """
        return self.current_state.name == state
        
    def get_state(self, state):
        """ Return the State instance with the passed name. """
        if state not in self.states:
            raise ValueError("State '%s' is not a registered state." % state)
        return self.states[state]

    def set_state(self, state):
        """ Set the current state. """
        if isinstance(state, basestring):
            state = self.get_state(state)
        self.current_state = state
        self.model.state = self.current_state.name
    
    def add_transition(self, trigger, source, dest, conditions=None, before=None, after=None):
        """ Create a new Transition instance and add it to the internal list.
        Args:
            trigger (string): The name of the method that will trigger the 
                transition. This will be attached to the currently specified 
                model (e.g., passing trigger='advance' will create a new 
                advance() method in the model that triggers the transition.)
            source(string): The name of the source state--i.e., the state we
                are transitioning away from.
            dest (string): The name of the destination State--i.e., the state 
                we are transitioning into.
            conditions (string or list): Condition(s) that must pass in order for 
                the transition to take place. Either a list providing the name 
                of a callable, or a list of callables. For the transition to 
                occur, ALL callables must return True.
            before (string or list): Callables to call before the transition.
            after (string or list): Callables to call after the transition.

        """
        if trigger not in self.events:
            self.events[trigger] = Event(trigger, self)
            setattr(self.model, trigger, self.events[trigger].trigger)

        if isinstance(source, basestring):
            source = self.states.keys() if source == '*' else [source]

        for s in source:
            t = Transition(s, dest, conditions, before, after)
            self.events[trigger].add_transition(t)

    def __getattr__(self, name):
        terms = name.split('_')
        if terms[0] in ['before', 'after']:
            name = '_'.join(terms[1:])
            print name
            if name not in self.events:
                raise MachineError('Event "%s" is not registered.' % name)
            return partial(self.events[name].add_callback, terms[0])
            
        elif name.startswith('on_enter') or name.startswith('on_exit'):
            state = self.get_state('_'.join(terms[2:]))
            return partial(state.add_callback, terms[1])


class MachineError(Exception):
    def __init__(self, value):
        self.value = value

    def __str__(self):
        return repr(self.value)



