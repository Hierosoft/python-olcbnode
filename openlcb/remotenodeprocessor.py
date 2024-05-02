import sys

from openlcb.eventid import EventID
from openlcb.node import Node
from openlcb.nodeid import NodeID
from openlcb.message import Message
from openlcb.mti import MTI
from openlcb.processor import Processor
from openlcb.pip import PIP
from openlcb.snip import SNIP

trace = False

class RemoteNodeProcessor(Processor) :
    '''
    'Handle incoming messages for a remote node, AKA an image node, representing some
    physical node out on the layout.

    Tracks node status, PIP and SNIP information, but deliberately does not
    track memory (config, CDI) contents due to size.
    '''

    def __init__(self, linkLayer=None) :
        # if(trace):
        #     print(" RemoteNodeProcessor-> __init__: ENTRY  \n\n")
        #     sys.stdout.flush()
        self.linkLayer = linkLayer

    def process(self, message, node) :
        # Do a fast drop of messages not to us, from us, or global - note linkLayer up/down are marked as global
        # if(trace):
        #     print(" RemoteNodeProcessor-> process: \n\n")
        #     sys.stdout.flush()
        if not ( message.mti.isGlobal()
                or self.checkSourceID(message, node)
                or self.checkDestID(message, node) ) :
            return False

        # if you see anything at all from us, must be in Initialized state
        if self.checkSourceID(message, node) :  # Sent by node we're processing?
            node.state = Node.State.Initialized # in case we came late to the party, must be in Initialized state

        # specific message handling
        if message.mti == MTI.Initialization_Complete or message.mti == MTI.Initialization_Complete_Simple:
                self.initializationComplete(message, node)
                return True
        elif message.mti == MTI.Protocol_Support_Reply:
            self.protocolSupportReply(message, node)
            return True
        elif message.mti == MTI.Link_Layer_Up:
            self.linkUpMessage(message, node)
        elif message.mti == MTI.Link_Layer_Down:
            self.linkDownMessage(message, node)
        elif message.mti == MTI.Simple_Node_Ident_Info_Request:
            self.simpleNodeIdentInfoRequest(message, node)
        elif message.mti == MTI.Simple_Node_Ident_Info_Reply:
            self.simpleNodeIdentInfoReply(message, node)
            return True
        elif message.mti == MTI.Producer_Identified_Active or message.mti == MTI.Producer_Identified_Inactive or message.mti == MTI.Producer_Identified_Unknown or message.mti == MTI.Producer_Consumer_Event_Report:
            self.producedEventIndicated(message, node)
            return True
        elif message.mti == MTI.Consumer_Identified_Active or message.mti == MTI.Consumer_Identified_Inactive or message.mti == MTI.Consumer_Identified_Unknown:
            self.consumedEventIndicated(message, node)
            return True
        elif message.mti == MTI.New_Node_Seen:
            self.newNodeSeen(message, node)
            return True
        else:
            return False

        ########################################################################################
        # THIS CODE WITH 'MATCH' INSTEAD OF 'IF/ELSE' SYNTAX OK WITH PYTHON >= TO VERSION 3.10 #
        ########################################################################################

        # specific message handling
        # match message.mti :
        #     case MTI.Initialization_Complete | MTI.Initialization_Complete_Simple :
        #         self.initializationComplete(message, node)
        #         return True
        #     case MTI.Protocol_Support_Reply :
        #         self.protocolSupportReply(message, node)
        #         return True
        #     case MTI.Link_Layer_Up :
        #         self.linkUpMessage(message, node)
        #     case MTI.Link_Layer_Down :
        #         self.linkDownMessage(message, node)
        #     case MTI.Simple_Node_Ident_Info_Request :
        #         self.simpleNodeIdentInfoRequest(message, node)
        #     case MTI.Simple_Node_Ident_Info_Reply :
        #         self.simpleNodeIdentInfoReply(message, node)
        #         return True
        #     case MTI.Producer_Identified_Active | MTI.Producer_Identified_Inactive | MTI.Producer_Identified_Unknown | MTI.Producer_Consumer_Event_Report :
        #         self.producedEventIndicated(message, node)
        #         return True
        #     case MTI.Consumer_Identified_Active | MTI.Consumer_Identified_Inactive | MTI.Consumer_Identified_Unknown :
        #         self.consumedEventIndicated(message, node)
        #         return True
        #     case MTI.New_Node_Seen :
        #         self.newNodeSeen(message, node)
        #         return True
        #     case _ :
        #         # we ignore others
        #         return False
        # return False

    def initializationComplete(self, message, node) :
        if self.checkSourceID(message, node) :  # Send by us?
            node.state = Node.State.Initialized
            # clear out PIP, SNIP caches - may have changed while node was offline
            node.pipSet = set(())
            node.snip = SNIP()

    def linkUpMessage(self, message, node) :
        # affects everybody
        node.state = Node.State.Uninitialized
        # don't clear out PIP, SNIP caches, they're probably still good

    def linkDownMessage(self, message, node) :
        # affects everybody
        node.state = Node.State.Uninitialized
        # don't clear out PIP, SNIP caches, they're probably still good

    def newNodeSeen(self, message, node) :
        if(trace):
            print("\n RemoteNodeProcessor->newNodeSeen: ENTRY sending out PIP, SNIP and IDENTIFY_EVENTS messages. \n")
            sys.stdout.flush()

        # send pip and snip requests for info from the new node
        pip = Message(MTI.Protocol_Support_Inquiry, self.linkLayer.localNodeID, node.id, [])
        self.linkLayer.sendMessage(pip)
        # We request SNIP data on startup so that we can display node names.  Can consider deferring this is it's a issue on big networks
        snip = Message(MTI.Simple_Node_Ident_Info_Request, self.linkLayer.localNodeID, node.id, [])
        self.linkLayer.sendMessage(snip)
        # we request produced and consumed event IDs
        eventReq = Message(MTI.Identify_Events_Addressed, self.linkLayer.localNodeID, node.id, [])
        self.linkLayer.sendMessage(eventReq)

    def protocolSupportReply(self, message, node) :
        if self.checkSourceID(message, node) : # sent by us?
            part0 = ((message.data[0]) << 24) if (len(message.data) > 0) else 0
            part1 = ((message.data[1]) << 16) if (len(message.data) > 1) else 0
            part2 = ((message.data[2]) <<  8) if (len(message.data) > 2) else 0
            part3 = ((message.data[3])      ) if (len(message.data) > 3) else 0

            content =  part0|part1|part2|part3
            if(trace):
                print(" RemoteNodeProcessor-> protocolSupportReply: PIP reply - (", message.data, ") \n\n")
                sys.stdout.flush()
            node.pipSet = PIP.setContentsFromInt(content)

    def simpleNodeIdentInfoRequest(self, message, node) :
        if self.checkDestID(message, node) : # sent by us? - overlapping SNIP activity is otherwise confusing
            # clear SNIP in the node to start accumulating
            node.snip = SNIP()

    def simpleNodeIdentInfoReply(self, message, node) :
        if self.checkSourceID(message, node) : # sent by this node? - overlapping SNIP activity is otherwise confusing
            # accumulate data in the node
            if(trace):
                print(" RemoteNodeProcessor-> simpleNodeIdentInfoReply: SNIP reply - (", message.data, ") \n\n")
                sys.stdout.flush()
            if len(message.data) > 2 :
                node.snip.addData(message.data)
                node.snip.updateStringsFromSnipData()

    def producedEventIndicated(self, message, node) :
        if self.checkSourceID(message, node) : # produced by this node?
            # make an event id from the data
            eventID = EventID(message.data)
            # register it
            node.events.produces(eventID)

    def consumedEventIndicated(self, message, node) :
        if self.checkSourceID(message, node) : # consumed by this node?
            # make an event id from the data
            eventID = EventID(message.data)
            # register it
            node.events.consumes(eventID)
